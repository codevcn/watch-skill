"""Base interface for installation-specific update strategies."""
from __future__ import annotations

import abc
import ssl
import urllib.request
from pathlib import Path

from watch_skill.errors import UpdateError
from watch_skill.policy import Channel, guard_egress
from watch_skill.update_engine.checksum import verify_file_sha256
from watch_skill.update_engine.models import (
    InstallationInfo,
    UpdateAsset,
    UpdatePlan,
    UpdateRelease,
    UpdateResult,
)


def _get_ssl_context() -> ssl.SSLContext:
    try:
        import certifi

        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()



class UpdateStrategy(abc.ABC):
    """Abstract strategy responsible for resolving and executing an update."""

    def __init__(self, info: InstallationInfo) -> None:
        self.info = info

    @abc.abstractmethod
    def plan(self, release: UpdateRelease, force: bool = False) -> UpdatePlan:
        """Evaluate release against installation and return a concrete plan."""
        raise NotImplementedError

    @abc.abstractmethod
    def apply(self, plan: UpdatePlan, dry_run: bool = False) -> UpdateResult:
        """Execute the planned update (or simulate if dry_run=True)."""
        raise NotImplementedError

    def download_and_verify(self, asset: UpdateAsset, target_path: Path) -> Path:
        """Download asset to target_path (.part staging) and verify against expected SHA-256."""
        guard_egress(Channel.SOURCE)
        if not asset.expected_sha256:
            raise UpdateError(
                f"Asset {asset.name} has no checksum recorded in SHA256SUMS.txt.",
                code="update.checksum_missing",
                fix=f"Visit https://github.com/codevcn/watch-skill/releases to check asset {asset.name}.",
            )

        target_path.parent.mkdir(parents=True, exist_ok=True)
        part_path = target_path.with_suffix(target_path.suffix + ".part")

        req = urllib.request.Request(
            asset.download_url,
            headers={"User-Agent": "watch-skill-updater"},
        )
        try:
            with (
                urllib.request.urlopen(req, context=_get_ssl_context(), timeout=60.0) as resp,
                open(part_path, "wb") as out,
            ):
                while chunk := resp.read(65536):
                    out.write(chunk)
        except Exception as exc:
            part_path.unlink(missing_ok=True)
            raise UpdateError(
                f"Failed to download asset {asset.name}: {exc}",
                code="update.download_failed",
                fix="Check your network connection and retry the update.",
            ) from exc

        if not verify_file_sha256(part_path, asset.expected_sha256):
            part_path.unlink(missing_ok=True)
            raise UpdateError(
                f"Downloaded file {asset.name} failed SHA-256 checksum verification.",
                code="update.hash_mismatch",
                fix="Retry running `watch-skill update`. If the error persists, download the release manually.",
            )

        part_path.replace(target_path)
        return target_path
