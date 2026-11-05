"""Data models for Watch Skill self-update operations."""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any


class InstallKind(StrEnum):
    """The detected packaging/environment kind."""

    WINDOWS_INNO = "windows_inno"
    WINDOWS_PORTABLE = "windows_portable"
    PIPX = "pipx"
    UV_TOOL = "uv_tool"
    VENV_PIP = "venv_pip"
    SYSTEM_PIP = "system_pip"
    EDITABLE_SOURCE = "editable_source"
    UVX_EPHEMERAL = "uvx_ephemeral"
    UNKNOWN = "unknown"


class UpdateStatus(StrEnum):
    """The high-level outcome of an update operation."""

    UP_TO_DATE = "up_to_date"
    AVAILABLE = "available"
    DRY_RUN = "dry_run"
    HANDOFF_STARTED = "handoff_started"
    UPDATED = "updated"


@dataclass
class InstallationInfo:
    """Provenance and layout details of the current running installation."""

    kind: InstallKind
    executable_path: Path
    version: str
    install_dir: Path | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind.value,
            "executable_path": str(self.executable_path),
            "version": self.version,
            "install_dir": str(self.install_dir) if self.install_dir else None,
            "metadata": self.metadata,
        }


@dataclass
class UpdateAsset:
    """An asset belonging to a GitHub release."""

    name: str
    download_url: str
    size: int
    expected_sha256: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "download_url": self.download_url,
            "size": self.size,
            "expected_sha256": self.expected_sha256,
        }


@dataclass
class UpdateRelease:
    """Authoritative metadata for a resolved release."""

    tag_name: str
    version: str
    published_at: str
    assets: list[UpdateAsset]
    checksums: dict[str, str] = field(default_factory=dict)

    def get_asset(self, name: str) -> UpdateAsset | None:
        for a in self.assets:
            if a.name == name:
                return a
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag_name": self.tag_name,
            "version": self.version,
            "published_at": self.published_at,
            "assets": [a.to_dict() for a in self.assets],
            "checksums_count": len(self.checksums),
        }


@dataclass
class UpdatePlan:
    """The concrete execution plan produced by plan_update."""

    current_version: str
    target_version: str
    install_kind: InstallKind
    strategy: str
    target_asset: UpdateAsset | None = None
    update_available: bool = False
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "current_version": self.current_version,
            "target_version": self.target_version,
            "install_kind": self.install_kind.value,
            "strategy": self.strategy,
            "update_available": self.update_available,
            "target_asset": self.target_asset.to_dict() if self.target_asset else None,
            "details": self.details,
        }


@dataclass
class UpdateResult:
    """Structured result returned by update operations for human/JSON surfaces."""

    ok: bool
    status: UpdateStatus
    current_version: str
    target_version: str
    update_available: bool
    install: dict[str, Any]
    strategy: str
    verification: dict[str, Any] | None = None
    transaction_id: str | None = None
    message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        res: dict[str, Any] = {
            "schema_version": 1,
            "ok": self.ok,
            "status": self.status.value,
            "current_version": self.current_version,
            "target_version": self.target_version,
            "update_available": self.update_available,
            "install": self.install,
            "strategy": self.strategy,
        }
        if self.verification is not None:
            res["verification"] = self.verification
        if self.transaction_id is not None:
            res["transaction_id"] = self.transaction_id
        if self.message is not None:
            res["message"] = self.message
        return res
