"""Update strategy handling Python packaging environments (pip, pipx, uv, editable)."""
from __future__ import annotations

from watch_skill.errors import UpdateError
from watch_skill.update_check import is_newer_version
from watch_skill.update_engine.models import (
    InstallKind,
    UpdatePlan,
    UpdateRelease,
    UpdateResult,
    UpdateStatus,
)
from watch_skill.update_engine.strategies.base import UpdateStrategy


class PythonEnvStrategy(UpdateStrategy):
    """Enforces provenance-aware update policies for Python environments."""

    def plan(self, release: UpdateRelease, force: bool = False) -> UpdatePlan:
        strategy_name = "editable_git" if self.info.kind == InstallKind.EDITABLE_SOURCE else "python_env"
        update_available = is_newer_version(release.version, self.info.version)
        return UpdatePlan(
            current_version=self.info.version,
            target_version=release.version,
            install_kind=self.info.kind,
            strategy=strategy_name,
            target_asset=None,
            update_available=update_available or force,
        )

    def apply(self, plan: UpdatePlan, dry_run: bool = False) -> UpdateResult:
        if self.info.kind == InstallKind.EDITABLE_SOURCE:
            raise UpdateError(
                "This installation is running from an editable source checkout.",
                code="update.editable_install",
                fix="Run `git pull && uv sync` in the repository root to update your development installation.",
            )

        if self.info.kind == InstallKind.UVX_EPHEMERAL:
            raise UpdateError(
                "This invocation is running ephemerally via uvx.",
                code="update.ephemeral_install",
                fix="Run uvx with the latest version or install persistently via pipx: pipx install watch-skill",
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
                message=f"Dry run: Target release {plan.target_version} verified. Python provenance gate active.",
            )

        # Provenance gate: PyPI package 'watch-skill' belongs to upstream oxbshw.
        # Refuse automated blind pip/pipx upgrades that would overwrite this distribution with upstream.
        raise UpdateError(
            "PyPI package 'watch-skill' is owned by upstream oxbshw. Automatic PyPI upgrade from this fork is prohibited to protect your installation.",
            code="update.unsupported_python_authority",
            fix="Install the standalone Windows installer from https://github.com/codevcn/watch-skill/releases or update directly from git: pip install -U git+https://github.com/codevcn/watch-skill.git",
        )
