"""Update strategy for Windows installations managed by Inno Setup."""
from __future__ import annotations

import os
import subprocess
import tempfile
import uuid
from pathlib import Path

from watch_skill.errors import UpdateError
from watch_skill.update_check import is_newer_version
from watch_skill.update_engine.models import (
    UpdatePlan,
    UpdateRelease,
    UpdateResult,
    UpdateStatus,
)
from watch_skill.update_engine.strategies.base import UpdateStrategy


class WindowsInnoStrategy(UpdateStrategy):
    """Orchestrates seamless Inno Setup silent installer handoff."""

    ASSET_NAME = "watch-skill-installer.exe"

    def plan(self, release: UpdateRelease, force: bool = False) -> UpdatePlan:
        asset = release.get_asset(self.ASSET_NAME)
        if not asset:
            raise UpdateError(
                f"Release {release.tag_name} does not provide {self.ASSET_NAME}.",
                code="update.no_compatible_asset",
                fix=f"Visit https://github.com/codevcn/watch-skill/releases/tag/{release.tag_name} to check assets.",
            )

        update_available = is_newer_version(release.version, self.info.version)
        if not update_available and not force:
            return UpdatePlan(
                current_version=self.info.version,
                target_version=release.version,
                install_kind=self.info.kind,
                strategy="inno_installer",
                target_asset=asset,
                update_available=False,
            )

        return UpdatePlan(
            current_version=self.info.version,
            target_version=release.version,
            install_kind=self.info.kind,
            strategy="inno_installer",
            target_asset=asset,
            update_available=True,
        )

    def apply(self, plan: UpdatePlan, dry_run: bool = False) -> UpdateResult:
        if not plan.target_asset:
            raise UpdateError(
                "Cannot apply update plan without target asset.",
                code="update.invalid_plan",
                fix="Re-run `watch-skill update` with a valid release.",
            )

        if dry_run:
            return UpdateResult(
                ok=True,
                status=UpdateStatus.DRY_RUN,
                current_version=plan.current_version,
                target_version=plan.target_version,
                update_available=plan.update_available,
                install=self.info.to_dict(),
                strategy=plan.strategy,
                message=f"Dry run: Inno installer {plan.target_asset.name} would be downloaded and spawned silently.",
            )

        tx_id = uuid.uuid4().hex[:12]
        temp_dir = Path(tempfile.gettempdir()) / f"watch-skill-update-{tx_id}"
        installer_path = temp_dir / self.ASSET_NAME

        # 1. Download and verify SHA-256
        self.download_and_verify(plan.target_asset, installer_path)

        # 2. Prepare log file and args
        log_dir = Path.home() / ".watch-skill"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"install-{tx_id}.log"

        cmd = [
            str(installer_path),
            "/SP-",
            "/VERYSILENT",
            "/SUPPRESSMSGBOXES",
            "/NORESTART",
            "/NORESTARTAPPLICATIONS",
            f"/LOG={log_file}",
        ]

        # 3. Spawn detached process
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
            )

        try:
            subprocess.Popen(
                cmd,
                creationflags=flags,
                close_fds=True,
                cwd=str(temp_dir),
            )
        except Exception as exc:
            raise UpdateError(
                f"Failed to launch Inno Setup installer: {exc}",
                code="update.spawn_failed",
                fix="Run the downloaded installer manually from: " + str(installer_path),
            ) from exc

        return UpdateResult(
            ok=True,
            status=UpdateStatus.HANDOFF_STARTED,
            current_version=plan.current_version,
            target_version=plan.target_version,
            update_available=plan.update_available,
            install=self.info.to_dict(),
            strategy=plan.strategy,
            verification={
                "sha256": "verified",
                "expected": plan.target_asset.expected_sha256,
            },
            transaction_id=tx_id,
            message="Installer process launched successfully. The application will be updated in the background.",
        )
