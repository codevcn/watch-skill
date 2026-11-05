"""Update engine core for Watch Skill."""
from __future__ import annotations

from watch_skill.update_engine.detection import detect_installation
from watch_skill.update_engine.lock import UpdateLock
from watch_skill.update_engine.models import (
    InstallationInfo,
    InstallKind,
    UpdateAsset,
    UpdatePlan,
    UpdateRelease,
    UpdateResult,
    UpdateStatus,
)
from watch_skill.update_engine.releases import fetch_latest_core_release
from watch_skill.update_engine.strategies import get_strategy

__all__ = [
    "InstallationInfo",
    "InstallKind",
    "UpdateAsset",
    "UpdateLock",
    "UpdatePlan",
    "UpdateRelease",
    "UpdateResult",
    "UpdateStatus",
    "detect_installation",
    "fetch_latest_core_release",
    "get_strategy",
]
