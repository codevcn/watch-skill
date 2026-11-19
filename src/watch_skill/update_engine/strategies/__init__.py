"""Strategy registry and factory for self-update implementations."""
from __future__ import annotations

from watch_skill.errors import UpdateError
from watch_skill.update_engine.models import InstallationInfo, InstallKind
from watch_skill.update_engine.strategies.base import UpdateStrategy
from watch_skill.update_engine.strategies.python_env import PythonEnvStrategy
from watch_skill.update_engine.strategies.windows_inno import WindowsInnoStrategy


def get_strategy(info: InstallationInfo) -> UpdateStrategy:
    """Select the appropriate update strategy based on verified installation provenance."""
    if info.kind == InstallKind.WINDOWS_INNO:
        return WindowsInnoStrategy(info)
    if info.kind in {
        InstallKind.EDITABLE_SOURCE,
        InstallKind.UVX_EPHEMERAL,
        InstallKind.PIPX,
        InstallKind.UV_TOOL,
        InstallKind.VENV_PIP,
        InstallKind.SYSTEM_PIP,
    }:
        return PythonEnvStrategy(info)

    if info.metadata.get("frozen"):
        raise UpdateError(
            "This frozen Watch Skill binary is not managed by the Windows Inno Setup installer and cannot self-update.",
            code="update.unsupported_environment",
            fix="Install Watch Skill using `watch-skill-installer.exe` from https://github.com/codevcn/watch-skill/releases.",
        )

    raise UpdateError(
        f"Cannot determine update strategy for installation kind: '{info.kind.value}'.",
        code="update.unsupported_environment",
        fix="Install Watch Skill using `watch-skill-installer.exe` from https://github.com/codevcn/watch-skill/releases.",
    )
