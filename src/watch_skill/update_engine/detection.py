"""Environment and installation provenance detection."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from watch_skill.update_engine.models import InstallationInfo, InstallKind


def _get_current_version() -> str:
    try:
        from watch_skill._version import __version__

        return __version__
    except ImportError:
        pass
    try:
        import tomllib

        root = Path(__file__).resolve().parents[3]
        pyproject = root / "pyproject.toml"
        if pyproject.is_file():
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
            return str(data.get("project", {}).get("version", "1.5.6"))
    except Exception:
        pass
    return "1.5.6"


def detect_installation(
    executable_override: Path | None = None,
    sys_frozen_override: bool | None = None,
) -> InstallationInfo:
    """Accurately identify how and where watch-skill is currently running."""
    exe_path = executable_override or Path(sys.executable).resolve()
    is_frozen = getattr(sys, "frozen", False) if sys_frozen_override is None else sys_frozen_override
    version = _get_current_version()
    install_dir = exe_path.parent

    # 1. Windows PyInstaller frozen binaries
    if is_frozen:
        marker = install_dir / ".watch-skill-install.json"
        if marker.is_file():
            try:
                data = json.loads(marker.read_text(encoding="utf-8"))
                if data.get("install_kind") == "windows_inno":
                    return InstallationInfo(
                        kind=InstallKind.WINDOWS_INNO,
                        executable_path=exe_path,
                        version=version,
                        install_dir=install_dir,
                        metadata=data,
                    )
            except Exception:
                pass

        # Legacy Inno Setup evidence: uninstaller present or installed under LocalAppData\Programs\watch-skill
        uninstaller_exists = (install_dir / "watch-skill-uninstaller.exe").is_file() or (
            install_dir / "unins000.exe"
        ).is_file()
        in_localappdata = "programs" in str(install_dir).lower() and "watch-skill" in str(install_dir).lower()

        if uninstaller_exists or in_localappdata:
            return InstallationInfo(
                kind=InstallKind.WINDOWS_INNO,
                executable_path=exe_path,
                version=version,
                install_dir=install_dir,
                metadata={"inno_heuristic": True, "uninstaller_exists": uninstaller_exists},
            )

        # Standalone portable binary
        return InstallationInfo(
            kind=InstallKind.WINDOWS_PORTABLE,
            executable_path=exe_path,
            version=version,
            install_dir=install_dir,
            metadata={"portable": True},
        )

    # 2. Python environment detection
    prefix = Path(sys.prefix).resolve()

    # Check for editable source checkout
    root_candidate = Path(__file__).resolve().parents[3]
    if (root_candidate / "pyproject.toml").is_file() and (root_candidate / ".git").is_dir():
        return InstallationInfo(
            kind=InstallKind.EDITABLE_SOURCE,
            executable_path=exe_path,
            version=version,
            install_dir=root_candidate,
            metadata={"source_root": str(root_candidate)},
        )

    # Check uv tool environment
    if (prefix / "uv-receipt.toml").is_file():
        return InstallationInfo(
            kind=InstallKind.UV_TOOL,
            executable_path=exe_path,
            version=version,
            install_dir=prefix,
            metadata={"uv_receipt": True},
        )

    # Check pipx managed environment
    if (prefix / "pipx_metadata.json").is_file():
        return InstallationInfo(
            kind=InstallKind.PIPX,
            executable_path=exe_path,
            version=version,
            install_dir=prefix,
            metadata={"pipx_metadata": True},
        )

    # Check virtualenv vs system Python
    is_venv = sys.prefix != getattr(sys, "base_prefix", sys.prefix)
    if is_venv:
        return InstallationInfo(
            kind=InstallKind.VENV_PIP,
            executable_path=exe_path,
            version=version,
            install_dir=prefix,
            metadata={"venv": True},
        )

    return InstallationInfo(
        kind=InstallKind.SYSTEM_PIP,
        executable_path=exe_path,
        version=version,
        install_dir=prefix,
        metadata={"system": True},
    )
