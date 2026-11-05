"""Update strategy for standalone portable Windows executables."""
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


class WindowsPortableStrategy(UpdateStrategy):
    """Replaces a standalone portable binary with atomic staging, smoke test, and rollback."""

    ASSET_NAME = "watch-skill-windows-x86_64.exe"

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
                strategy="portable_replace",
                target_asset=asset,
                update_available=False,
            )

        return UpdatePlan(
            current_version=self.info.version,
            target_version=release.version,
            install_kind=self.info.kind,
            strategy="portable_replace",
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

        exe_path = self.info.executable_path
        install_dir = exe_path.parent

        # Verify directory writability
        if not os.access(str(install_dir), os.W_OK):
            raise UpdateError(
                f"Directory '{install_dir}' is not writable. Cannot update portable executable.",
                code="update.permission_denied",
                fix=f"Run the update from an elevated shell or move {exe_path.name} to a writable folder.",
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
                message=f"Dry run: Portable binary {plan.target_asset.name} would be staged and replaced.",
            )

        tx_id = uuid.uuid4().hex[:12]
        staged_new = install_dir / f"{exe_path.stem}.new-{tx_id}.exe"
        backup_path = install_dir / f"{exe_path.name}.bak"

        # 1. Download and verify SHA-256
        self.download_and_verify(plan.target_asset, staged_new)

        # 2. Generate updater script that handles PID wait, rename, smoke check, and rollback
        current_pid = os.getpid()
        script_path = Path(tempfile.gettempdir()) / f"watch-skill-update-{tx_id}.ps1"

        script_content = f"""# PowerShell Self-Update Helper
$targetPid = {current_pid}
$activeExe = "{exe_path}"
$stagedExe = "{staged_new}"
$backupExe = "{backup_path}"

# 1. Wait for parent process to exit
$timeout = 30
while ($timeout -gt 0) {{
    $proc = Get-Process -Id $targetPid -ErrorAction SilentlyContinue
    if (-not $proc) {{ break }}
    Start-Sleep -Milliseconds 500
    $timeout--
}}

# 2. Atomic replacement
try {{
    if (Test-Path -LiteralPath $backupExe) {{ Remove-Item -LiteralPath $backupExe -Force -ErrorAction SilentlyContinue }}
    Move-Item -LiteralPath $activeExe -Destination $backupExe -Force
    Move-Item -LiteralPath $stagedExe -Destination $activeExe -Force

    # 3. Smoke test
    $output = & "$activeExe" --version
    if ($LASTEXITCODE -eq 0) {{
        Remove-Item -LiteralPath $backupExe -Force -ErrorAction SilentlyContinue
        Remove-Item -LiteralPath $MyInvocation.MyCommand.Path -Force -ErrorAction SilentlyContinue
        exit 0
    }} else {{
        # Rollback on smoke test failure
        Move-Item -LiteralPath $backupExe -Destination $activeExe -Force
        exit 1
    }}
}} catch {{
    if (Test-Path -LiteralPath $backupExe) {{
        Move-Item -LiteralPath $backupExe -Destination $activeExe -Force -ErrorAction SilentlyContinue
    }}
    exit 1
}}
"""
        script_path.write_text(script_content, encoding="utf-8")

        # 3. Launch helper script detached
        flags = 0
        if os.name == "nt":
            flags = getattr(subprocess, "DETACHED_PROCESS", 0x00000008) | getattr(
                subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200
            )

        cmd = [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script_path),
        ]

        try:
            subprocess.Popen(
                cmd,
                creationflags=flags,
                close_fds=True,
                cwd=str(install_dir),
            )
        except Exception as exc:
            staged_new.unlink(missing_ok=True)
            script_path.unlink(missing_ok=True)
            raise UpdateError(
                f"Failed to launch portable update helper script: {exc}",
                code="update.spawn_failed",
                fix=f"Replace '{exe_path}' manually with '{staged_new}'.",
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
            message="Portable update handoff started with automatic rollback protection. Exiting current process.",
        )
