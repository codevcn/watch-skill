"""Public API for Watch Skill self-update operations."""
from __future__ import annotations

from watch_skill.update_engine.detection import detect_installation
from watch_skill.update_engine.lock import UpdateLock
from watch_skill.update_engine.models import (
    UpdatePlan,
    UpdateResult,
    UpdateStatus,
)
from watch_skill.update_engine.releases import DEFAULT_REPO, fetch_latest_core_release
from watch_skill.update_engine.strategies import get_strategy


def check_update(repo: str = DEFAULT_REPO) -> UpdateResult:
    """Perform a fresh, authoritative update check without mutating anything."""
    info = detect_installation()
    release = fetch_latest_core_release(repo=repo)
    strategy = get_strategy(info)
    plan = strategy.plan(release, force=False)

    if plan.update_available:
        return UpdateResult(
            ok=True,
            status=UpdateStatus.AVAILABLE,
            current_version=info.version,
            target_version=release.version,
            update_available=True,
            install=info.to_dict(),
            strategy=plan.strategy,
            message=f"Update available: {info.version} -> {release.version}",
        )

    return UpdateResult(
        ok=True,
        status=UpdateStatus.UP_TO_DATE,
        current_version=info.version,
        target_version=release.version,
        update_available=False,
        install=info.to_dict(),
        strategy=plan.strategy,
        message=f"watch-skill is already up-to-date (version {info.version}).",
    )


def plan_update(repo: str = DEFAULT_REPO, force: bool = False) -> UpdatePlan:
    """Generate an authoritative update plan without executing it."""
    info = detect_installation()
    release = fetch_latest_core_release(repo=repo)
    strategy = get_strategy(info)
    return strategy.plan(release, force=force)


def run_update(
    check_only: bool = False,
    dry_run: bool = False,
    force: bool = False,
    repo: str = DEFAULT_REPO,
) -> UpdateResult:
    """Execute the canonical self-update workflow."""
    if check_only:
        return check_update(repo=repo)

    info = detect_installation()
    # Concurrency lock covers release fetch, download, verification, and handoff
    with UpdateLock(target_version="pending"):
        release = fetch_latest_core_release(repo=repo)
        strategy = get_strategy(info)
        plan = strategy.plan(release, force=force)

        if not plan.update_available and not force:
            return UpdateResult(
                ok=True,
                status=UpdateStatus.UP_TO_DATE,
                current_version=info.version,
                target_version=release.version,
                update_available=False,
                install=info.to_dict(),
                strategy=plan.strategy,
                message=f"watch-skill is already up-to-date (version {info.version}).",
            )

        return strategy.apply(plan, dry_run=dry_run)
