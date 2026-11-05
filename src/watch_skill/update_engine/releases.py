"""Release resolution and asset discovery from GitHub Releases."""
from __future__ import annotations

import json
import ssl
import urllib.error
import urllib.request
from typing import Any

from watch_skill.errors import PolicyError, UpdateError
from watch_skill.policy import Channel, guard_egress
from watch_skill.update_check import _parse_version, extract_version_from_tag
from watch_skill.update_engine.checksum import parse_sha256sums
from watch_skill.update_engine.models import UpdateAsset, UpdateRelease

DEFAULT_REPO = "codevcn/watch-skill"
REQUEST_TIMEOUT_SECONDS = 15.0


def _get_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def _request_json(url: str) -> Any:
    """Fetch and parse JSON with policy enforcement and user-agent."""
    guard_egress(Channel.SOURCE)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "watch-skill-updater",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return json.loads(response.read().decode("utf-8"))


def _request_text(url: str) -> str:
    """Fetch text content with policy enforcement."""
    guard_egress(Channel.SOURCE)
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "watch-skill-updater",
            "Accept": "*/*",
        },
    )
    with urllib.request.urlopen(req, context=_get_ssl_context(), timeout=REQUEST_TIMEOUT_SECONDS) as response:
        return response.read().decode("utf-8")


def fetch_latest_core_release(repo: str = DEFAULT_REPO) -> UpdateRelease:
    """Query GitHub API to find the newest stable core-v* release and parse its checksums."""
    try:
        guard_egress(Channel.SOURCE)
    except PolicyError as exc:
        raise UpdateError(
            "Offline policy prohibits checking for online updates.",
            code="update.offline",
            fix="Unset WATCHSKILL_OFFLINE or enable network in settings to allow update checks.",
        ) from exc

    url = f"https://api.github.com/repos/{repo}/releases?per_page=30"
    try:
        releases = _request_json(url)
    except urllib.error.URLError as exc:
        raise UpdateError(
            f"Failed to fetch releases from GitHub: {exc}",
            code="update.network_error",
            fix="Check your internet connection and verify GitHub is reachable.",
        ) from exc
    except json.JSONDecodeError as exc:
        raise UpdateError(
            "Received invalid JSON response from GitHub API.",
            code="update.invalid_release",
            fix="Retry running the update command.",
        ) from exc

    if not isinstance(releases, list):
        raise UpdateError(
            "GitHub API returned unexpected data structure.",
            code="update.invalid_release",
            fix="Check repository settings or retry later.",
        )

    # Filter for non-draft, non-prerelease tags starting with core-v
    candidates: list[dict[str, Any]] = []
    for rel in releases:
        if not isinstance(rel, dict):
            continue
        if rel.get("draft") or rel.get("prerelease"):
            continue
        tag = str(rel.get("tag_name", ""))
        if tag.startswith("core-v"):
            candidates.append(rel)

    if not candidates:
        raise UpdateError(
            f"No stable core releases found in repository {repo}.",
            code="update.no_compatible_release",
            fix=f"Visit https://github.com/{repo}/releases to check available downloads.",
        )

    # Pick the highest semver release
    best_release = max(
        candidates,
        key=lambda r: _parse_version(extract_version_from_tag(str(r.get("tag_name", "")))),
    )

    tag_name = str(best_release.get("tag_name", ""))
    version = extract_version_from_tag(tag_name)
    published_at = str(best_release.get("published_at", ""))

    # Parse assets
    assets_raw = best_release.get("assets", [])
    checksums_url: str | None = None
    assets: list[UpdateAsset] = []

    for item in assets_raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name", ""))
        download_url = str(item.get("browser_download_url", ""))
        size = int(item.get("size", 0))
        if name == "SHA256SUMS.txt":
            checksums_url = download_url
        else:
            assets.append(UpdateAsset(name=name, download_url=download_url, size=size))

    if not checksums_url:
        raise UpdateError(
            f"Release {tag_name} is missing required SHA256SUMS.txt checksum file.",
            code="update.checksum_missing",
            fix=f"Check release integrity at https://github.com/{repo}/releases/tag/{tag_name}.",
        )

    # Fetch and parse SHA256SUMS.txt
    try:
        checksums_text = _request_text(checksums_url)
        checksums = parse_sha256sums(checksums_text)
    except Exception as exc:
        raise UpdateError(
            f"Failed to fetch SHA256SUMS.txt from release {tag_name}: {exc}",
            code="update.checksum_missing",
            fix="Verify network connectivity and retry.",
        ) from exc

    # Map checksums onto assets
    for asset in assets:
        if asset.name in checksums:
            asset.expected_sha256 = checksums[asset.name]

    return UpdateRelease(
        tag_name=tag_name,
        version=version,
        published_at=published_at,
        assets=assets,
        checksums=checksums,
    )
