"""Offline unit test suite for Watch Skill self-update engine and CLI command."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from watch_skill.errors import UpdateError
from watch_skill.surfaces.cli.main import app
from watch_skill.update_engine.checksum import (
    compute_file_sha256,
    parse_sha256sums,
    verify_file_sha256,
)
from watch_skill.update_engine.detection import detect_installation
from watch_skill.update_engine.lock import UpdateLock
from watch_skill.update_engine.models import (
    InstallationInfo,
    InstallKind,
    UpdateAsset,
    UpdateRelease,
    UpdateResult,
    UpdateStatus,
)
from watch_skill.update_engine.releases import fetch_latest_core_release
from watch_skill.update_engine.strategies.python_env import PythonEnvStrategy
from watch_skill.update_engine.strategies.windows_inno import WindowsInnoStrategy

runner = CliRunner()


# ── Checksum Parsing & Verification ──────────────────────────────────────────


def test_parse_sha256sums_valid() -> None:
    text = (
        "# Release Checksums\n"
        "a43dd9e28b4c713a479a037b581c47b3c3878ae24b6ddbb9a9a606c4ed521afe  watch-skill-installer.exe\n"
        "ef2b5ee8427f22c95acdfc3436fa4799eca735896804c1b4479305d9c90887f1 *watch-skill-windows-x86_64.exe\n"
    )
    res = parse_sha256sums(text)
    assert res["watch-skill-installer.exe"] == "a43dd9e28b4c713a479a037b581c47b3c3878ae24b6ddbb9a9a606c4ed521afe"
    assert res["watch-skill-windows-x86_64.exe"] == "ef2b5ee8427f22c95acdfc3436fa4799eca735896804c1b4479305d9c90887f1"


def test_file_sha256_verification(tmp_path: Path) -> None:
    dummy = tmp_path / "test.bin"
    dummy.write_bytes(b"hello watch-skill self-update")
    digest = compute_file_sha256(dummy)
    assert len(digest) == 64
    assert verify_file_sha256(dummy, digest)
    assert not verify_file_sha256(dummy, "0" * 64)


# ── Environment & Provenance Detection ───────────────────────────────────────


def test_detect_inno_with_marker(tmp_path: Path) -> None:
    exe = tmp_path / "watch-skill.exe"
    exe.write_text("", encoding="utf-8")
    marker = tmp_path / ".watch-skill-install.json"
    marker.write_text('{"install_kind": "windows_inno", "version": "1.5.6"}', encoding="utf-8")

    info = detect_installation(executable_override=exe, sys_frozen_override=True)
    assert info.kind == InstallKind.WINDOWS_INNO
    assert info.metadata.get("install_kind") == "windows_inno"


def test_detect_inno_with_legacy_heuristic(tmp_path: Path) -> None:
    prog_dir = tmp_path / "Programs" / "watch-skill"
    prog_dir.mkdir(parents=True)
    exe = prog_dir / "watch-skill.exe"
    exe.write_text("", encoding="utf-8")
    (prog_dir / "watch-skill-uninstaller.exe").write_text("", encoding="utf-8")

    info = detect_installation(executable_override=exe, sys_frozen_override=True)
    assert info.kind == InstallKind.WINDOWS_INNO


def test_detect_portable_when_frozen_without_inno(tmp_path: Path) -> None:
    portable_dir = tmp_path / "Downloads"
    portable_dir.mkdir(parents=True)
    exe = portable_dir / "watch-skill.exe"
    exe.write_text("", encoding="utf-8")

    info = detect_installation(executable_override=exe, sys_frozen_override=True)
    assert info.kind == InstallKind.WINDOWS_PORTABLE


def test_detect_editable_source(tmp_path: Path) -> None:
    info = detect_installation(executable_override=tmp_path / "python.exe", sys_frozen_override=False)
    # The active test workspace is indeed an editable git checkout
    assert info.kind == InstallKind.EDITABLE_SOURCE


# ── Release Resolution & Integrity ──────────────────────────────────────────


SAMPLE_RELEASES = [
    {
        "tag_name": "deepwatch-v0.1.4",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-01T10:00:00Z",
        "assets": [],
    },
    {
        "tag_name": "core-v1.6.0-rc1",
        "draft": False,
        "prerelease": True,
        "published_at": "2026-11-02T10:00:00Z",
        "assets": [],
    },
    {
        "tag_name": "core-v1.6.0",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-11-03T10:00:00Z",
        "assets": [
            {
                "name": "watch-skill-installer.exe",
                "browser_download_url": "https://github.com/codevcn/watch-skill/releases/download/core-v1.6.0/watch-skill-installer.exe",
                "size": 25000000,
            },
            {
                "name": "watch-skill-windows-x86_64.exe",
                "browser_download_url": "https://github.com/codevcn/watch-skill/releases/download/core-v1.6.0/watch-skill-windows-x86_64.exe",
                "size": 29000000,
            },
            {
                "name": "SHA256SUMS.txt",
                "browser_download_url": "https://github.com/codevcn/watch-skill/releases/download/core-v1.6.0/SHA256SUMS.txt",
                "size": 300,
            },
        ],
    },
    {
        "tag_name": "core-v1.5.6",
        "draft": False,
        "prerelease": False,
        "published_at": "2026-10-25T10:00:00Z",
        "assets": [],
    },
]

SAMPLE_CHECKSUMS = (
    "1111111111111111111111111111111111111111111111111111111111111111  watch-skill-installer.exe\n"
    "2222222222222222222222222222222222222222222222222222222222222222  watch-skill-windows-x86_64.exe\n"
)


@patch("watch_skill.update_engine.releases._request_text", return_value=SAMPLE_CHECKSUMS)
@patch("watch_skill.update_engine.releases._request_json", return_value=SAMPLE_RELEASES)
def test_fetch_latest_core_release_filters_correctly(mock_json: MagicMock, mock_text: MagicMock) -> None:
    rel = fetch_latest_core_release(repo="codevcn/watch-skill")
    assert rel.tag_name == "core-v1.6.0"
    assert rel.version == "1.6.0"
    assert rel.checksums["watch-skill-installer.exe"] == "1" * 64
    installer = rel.get_asset("watch-skill-installer.exe")
    assert installer is not None
    assert installer.expected_sha256 == "1" * 64


def test_fetch_release_refused_under_offline() -> None:
    from watch_skill.policy import ExecutionPolicy, use_policy

    offline_pol = ExecutionPolicy(offline=True, allow_source_network=False)
    with use_policy(offline_pol), pytest.raises(UpdateError) as exc_info:
        fetch_latest_core_release()

    assert exc_info.value.code == "update.offline"
    assert exc_info.value.fix is not None


# ── Strategies & Rollback Mechanics ──────────────────────────────────────────


def test_inno_strategy_planning(tmp_path: Path) -> None:
    info = InstallationInfo(
        kind=InstallKind.WINDOWS_INNO,
        executable_path=tmp_path / "watch-skill.exe",
        version="1.5.6",
    )
    strat = WindowsInnoStrategy(info)

    rel = UpdateRelease(
        tag_name="core-v1.6.0",
        version="1.6.0",
        published_at="",
        assets=[
            UpdateAsset(
                name="watch-skill-installer.exe",
                download_url="https://fake/installer.exe",
                size=1000,
                expected_sha256="a" * 64,
            )
        ],
    )

    plan = strat.plan(rel)
    assert plan.update_available is True
    assert plan.target_version == "1.6.0"
    assert plan.strategy == "inno_installer"

    # Dry-run execution
    result = strat.apply(plan, dry_run=True)
    assert result.status == UpdateStatus.DRY_RUN
    assert result.ok is True


def test_python_env_strategy_guards_upstream_pypi(tmp_path: Path) -> None:
    info = InstallationInfo(
        kind=InstallKind.PIPX,
        executable_path=tmp_path / "watch-skill.exe",
        version="1.5.6",
    )
    strat = PythonEnvStrategy(info)
    rel = UpdateRelease(tag_name="core-v1.6.0", version="1.6.0", published_at="", assets=[])

    plan = strat.plan(rel)
    assert plan.update_available is True

    # Attempting apply must refuse blind PyPI upgrade (AC-08)
    with pytest.raises(UpdateError) as exc_info:
        strat.apply(plan, dry_run=False)

    assert exc_info.value.code == "update.unsupported_python_authority"
    assert "upstream oxbshw" in exc_info.value.message
    assert exc_info.value.fix is not None


def test_python_env_strategy_refuses_editable_source(tmp_path: Path) -> None:
    info = InstallationInfo(
        kind=InstallKind.EDITABLE_SOURCE,
        executable_path=tmp_path / "python.exe",
        version="1.5.6",
    )
    strat = PythonEnvStrategy(info)
    rel = UpdateRelease(tag_name="core-v1.6.0", version="1.6.0", published_at="", assets=[])

    plan = strat.plan(rel)
    assert plan.strategy == "editable_git"

    with pytest.raises(UpdateError) as exc_info:
        strat.apply(plan, dry_run=False)

    assert exc_info.value.code == "update.editable_install"
    assert "git pull && uv sync" in str(exc_info.value.fix)


# ── Concurrency & Locking ────────────────────────────────────────────────────


def test_concurrency_lock_second_process_rejected(tmp_path: Path) -> None:
    lock_file = tmp_path / "update.lock"
    lock1 = UpdateLock(lock_path=lock_file, target_version="1.6.0")
    lock1.acquire()

    lock2 = UpdateLock(lock_path=lock_file, target_version="1.6.0")
    with pytest.raises(UpdateError) as exc_info:
        lock2.acquire()

    assert exc_info.value.code == "update.in_progress"
    lock1.release()

    # After release, lock2 should acquire cleanly
    lock2.acquire()
    lock2.release()


# ── CLI Surface & --json Contract ────────────────────────────────────────────


def test_cli_update_check_json_mocked() -> None:
    sample_res = UpdateResult(
        ok=True,
        status=UpdateStatus.AVAILABLE,
        current_version="1.5.6",
        target_version="1.6.0",
        update_available=True,
        install={"kind": "windows_inno"},
        strategy="inno_installer",
        message="Update available: 1.5.6 -> 1.6.0",
    )

    with patch("watch_skill.update.check_update", return_value=sample_res):
        res = runner.invoke(app, ["update", "--check", "--json"])

    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["status"] == "available"
    assert data["update_available"] is True
    assert data["target_version"] == "1.6.0"


def test_cli_update_dry_run_json_mocked() -> None:
    sample_res = UpdateResult(
        ok=True,
        status=UpdateStatus.DRY_RUN,
        current_version="1.5.6",
        target_version="1.6.0",
        update_available=True,
        install={"kind": "windows_inno"},
        strategy="inno_installer",
        message="Dry run simulation.",
    )

    with patch("watch_skill.update.run_update", return_value=sample_res):
        res = runner.invoke(app, ["update", "--dry-run", "--json"])

    assert res.exit_code == 0
    data = json.loads(res.stdout)
    assert data["ok"] is True
    assert data["status"] == "dry_run"


def test_cli_update_conflicting_flags_rejected() -> None:
    res = runner.invoke(app, ["update", "--check", "--dry-run", "--json"])
    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert data["ok"] is False
    assert data["error"]["code"] == "update.invalid_arguments"
    assert data["error"]["fix"] is not None


def test_cli_update_error_envelope_json() -> None:
    with patch(
        "watch_skill.update.run_update",
        side_effect=UpdateError(
            "Downloaded file failed checksum verification.",
            code="update.hash_mismatch",
            fix="Retry running watch-skill update.",
        ),
    ):
        res = runner.invoke(app, ["update", "--json"])

    assert res.exit_code == 1
    data = json.loads(res.stdout)
    assert data["ok"] is False
    assert data["error"]["code"] == "update.hash_mismatch"
    assert data["error"]["fix"] == "Retry running watch-skill update."
