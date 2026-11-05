"""Non-blocking update checker for Watch Skill CLI.

Checks for newer Core releases on GitHub in a background daemon thread, caching
the result for 24 hours. Emits update notices exclusively to sys.stderr so
machine-readable stdout (--json) is never polluted.

Guards:
- WATCHSKILL_NO_UPDATE_CHECK=1 disables all update checks.
- WATCHSKILL_OFFLINE=1 or settings.offline disables all outbound calls.
- Timeout is strictly <= 2.5s.
- Product-specific: filters releases list for core-v* tags to prevent crossed wires with DeepWatch.
- Cross-process file locking prevents request storms on concurrent invocations.
- Failure backoff updates checked_at to avoid hammering GitHub on rate limit/timeout.
- All network and parsing errors are silently caught.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

DEFAULT_REPO = "codevcn/watch-skill"
CACHE_TTL_SECONDS = 86400.0  # 24 hours
LOCK_STALE_SECONDS = 60.0  # 60 seconds
REQUEST_TIMEOUT_SECONDS = 2.5
SCHEMA_VERSION = 1


def extract_version_from_tag(tag: str) -> str:
    """Extract clean semver string from tags like core-v1.5.6 or v1.5.6."""
    clean = tag.strip()
    if clean.startswith("core-v"):
        clean = clean[len("core-v"):]
    elif clean.startswith("deepwatch-v"):
        clean = clean[len("deepwatch-v"):]
    elif clean.startswith("v"):
        clean = clean[1:]
    return clean.strip()


def _parse_version(v_str: str) -> tuple[int, ...]:
    """Parse semver string into a comparable tuple fallback-safe."""
    try:
        from packaging.version import parse as pkg_parse

        v = pkg_parse(v_str)
        return (v.major, v.minor, v.micro)
    except Exception:
        parts = []
        for segment in extract_version_from_tag(v_str).split("."):
            num = ""
            for ch in segment:
                if ch.isdigit():
                    num += ch
                else:
                    break
            parts.append(int(num) if num else 0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])


def is_newer_version(latest: str, current: str) -> bool:
    """Return True if latest is strictly newer than current."""
    try:
        return _parse_version(latest) > _parse_version(current)
    except Exception:
        return False


def get_update_cache_path() -> Path:
    """Resolve path to ~/.watch-skill/update-check.json."""
    try:
        from watch_skill.config import get_settings

        return get_settings().data_dir / "update-check.json"
    except Exception:
        return Path.home() / ".watch-skill" / "update-check.json"


def _read_cache(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict) and data.get("schema_version") == SCHEMA_VERSION:
            return data
    except Exception:
        pass
    return None


def _write_cache(path: Path, data: dict[str, Any]) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        tmp.replace(path)
    except Exception:
        pass


def _acquire_lock(lock_path: Path) -> bool:
    """Acquire cross-process atomic lock file with stale recovery."""
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        if lock_path.is_file():
            try:
                mtime = lock_path.stat().st_mtime
                if (time.time() - mtime) > LOCK_STALE_SECONDS:
                    lock_path.unlink(missing_ok=True)
            except OSError:
                pass

        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, "w") as f:
            f.write(f"{os.getpid()}\n{time.time()}\n")
        return True
    except OSError:
        return False


def _release_lock(lock_path: Path) -> None:
    """Release atomic lock file safely."""
    try:
        lock_path.unlink(missing_ok=True)
    except OSError:
        pass


def _fetch_latest_release(repo: str, current_version: str, cache_path: Path, existing_cache: dict[str, Any] | None) -> None:
    """Background worker: fetch releases from GitHub API, filter for Core train, merge state, and update cache."""
    lock_path = cache_path.with_suffix(".lock")
    if not _acquire_lock(lock_path):
        return

    try:
        # Query recent releases to find the latest Watch Core release, isolating from DeepWatch
        url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
        req = urllib.request.Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"watch-skill/{current_version}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        if existing_cache and existing_cache.get("etag"):
            req.add_header("If-None-Match", existing_cache["etag"])

        now_iso = datetime.now(UTC).isoformat()

        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_SECONDS) as resp:
                etag = resp.headers.get("ETag")
                raw = resp.read().decode("utf-8")
                payload = json.loads(raw)
        except urllib.error.HTTPError:
            fresh_cache = _read_cache(cache_path) or existing_cache or {}
            updated = dict(fresh_cache)
            updated["schema_version"] = SCHEMA_VERSION
            updated["checked_at"] = now_iso
            _write_cache(cache_path, updated)
            return
        except Exception:
            # Failure backoff: update checked_at timestamp so subsequent commands don't hammer
            fresh_cache = _read_cache(cache_path) or existing_cache or {}
            updated = dict(fresh_cache)
            updated["schema_version"] = SCHEMA_VERSION
            updated["checked_at"] = now_iso
            _write_cache(cache_path, updated)
            return

        if not isinstance(payload, list):
            return

        # Product-specific release discovery: prioritize core-v* tags, fallback to legacy v*
        latest_core_release = None
        for rel in payload:
            if rel.get("draft") or rel.get("prerelease"):
                continue
            tag = rel.get("tag_name", "")
            if tag.startswith("core-v"):
                latest_core_release = rel
                break

        if not latest_core_release:
            for rel in payload:
                if rel.get("draft") or rel.get("prerelease"):
                    continue
                tag = rel.get("tag_name", "")
                if tag.startswith("core-v") or tag.startswith("v"):
                    latest_core_release = rel
                    break

        if not latest_core_release:
            return

        raw_tag = latest_core_release.get("tag_name", "")
        clean_version = extract_version_from_tag(raw_tag)
        release_url = latest_core_release.get("html_url", f"https://github.com/{repo}/releases/tag/{raw_tag}")

        # Merge state: read the freshest disk cache to preserve last_notified_version
        fresh_cache = _read_cache(cache_path) or existing_cache or {}
        cache_data = {
            "schema_version": SCHEMA_VERSION,
            "checked_at": now_iso,
            "latest_version": clean_version,
            "release_url": release_url,
            "etag": etag,
            "last_notified_at": fresh_cache.get("last_notified_at"),
            "last_notified_version": fresh_cache.get("last_notified_version"),
        }
        _write_cache(cache_path, cache_data)
    finally:
        _release_lock(lock_path)


def check_for_updates() -> None:
    """Entry point for checking updates during CLI invocation.

    Non-blocking: reads local cache immediately and emits notice to stderr if
    a newer version is known. If the cache is missing or older than 24h,
    spawns a background worker thread with cross-process locking.
    """
    if os.environ.get("WATCHSKILL_NO_UPDATE_CHECK") == "1":
        return
    if os.environ.get("WATCHSKILL_OFFLINE") == "1":
        return

    try:
        from watch_skill.config import get_settings

        if get_settings().offline:
            return
    except Exception:
        pass

    try:
        from watch_skill import __version__ as current_version
    except Exception:
        current_version = "0.0.0"

    repo = os.environ.get("WATCHSKILL_UPDATE_REPO", DEFAULT_REPO)
    cache_path = get_update_cache_path()
    cache = _read_cache(cache_path)

    # 1. Notify if cache indicates a newer release and hasn't notified yet
    if cache:
        latest = cache.get("latest_version")
        release_url = cache.get("release_url", f"https://github.com/{repo}/releases/latest")
        if latest and is_newer_version(latest, current_version):
            last_notified = cache.get("last_notified_version")
            if last_notified != latest:
                sys.stderr.write(
                    f"\n[watch-skill] Update available: {current_version} \u2192 {latest}\n"
                    f"Download: {release_url}\n\n"
                )
                sys.stderr.flush()
                # Update last_notified_version in cache
                updated = dict(cache)
                updated["last_notified_version"] = latest
                updated["last_notified_at"] = datetime.now(UTC).isoformat()
                _write_cache(cache_path, updated)
                cache = updated

    # 2. Check if cache is stale or missing
    needs_refresh = False
    if not cache:
        needs_refresh = True
    else:
        checked_at_str = cache.get("checked_at")
        if not checked_at_str:
            needs_refresh = True
        else:
            try:
                checked_at = datetime.fromisoformat(checked_at_str)
                age = (datetime.now(UTC) - checked_at).total_seconds()
                if age >= CACHE_TTL_SECONDS:
                    needs_refresh = True
            except Exception:
                needs_refresh = True

    if needs_refresh:
        worker = threading.Thread(
            target=_fetch_latest_release,
            args=(repo, current_version, cache_path, cache),
            daemon=True,
            name="watch-skill-update-check",
        )
        worker.start()
