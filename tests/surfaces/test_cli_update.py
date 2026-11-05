"""Tests for the non-blocking CLI update checker."""
from __future__ import annotations

import io
import json
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from watch_skill.update_check import (
    SCHEMA_VERSION,
    _fetch_latest_release,
    _read_cache,
    _write_cache,
    check_for_updates,
    is_newer_version,
)


def test_is_newer_version():
    assert is_newer_version("1.6.0", "1.5.3") is True
    assert is_newer_version("2.0.0", "1.5.3") is True
    assert is_newer_version("1.5.4", "1.5.3") is True
    assert is_newer_version("1.5.3", "1.5.3") is False
    assert is_newer_version("1.5.2", "1.5.3") is False
    assert is_newer_version("1.4.99", "1.5.3") is False


def test_cache_read_write(tmp_path: Path):
    cache_file = tmp_path / "update-check.json"
    assert _read_cache(cache_file) is None

    # Corrupt content
    cache_file.write_text("invalid json", encoding="utf-8")
    assert _read_cache(cache_file) is None

    # Valid schema
    data = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "latest_version": "1.6.0",
        "release_url": "https://github.com/codevcn/watch-skill/releases/tag/v1.6.0",
        "etag": "12345",
        "last_notified_at": None,
        "last_notified_version": None,
    }
    _write_cache(cache_file, data)
    read_back = _read_cache(cache_file)
    assert read_back is not None
    assert read_back["latest_version"] == "1.6.0"
    assert read_back["etag"] == "12345"


def test_check_for_updates_disabled_by_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cache_file = tmp_path / "update-check.json"
    monkeypatch.setenv("WATCHSKILL_NO_UPDATE_CHECK", "1")

    with patch("watch_skill.update_check.get_update_cache_path", return_value=cache_file):
        with patch("threading.Thread") as mock_thread:
            check_for_updates()
            mock_thread.assert_not_called()


def test_check_for_updates_disabled_by_offline_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cache_file = tmp_path / "update-check.json"
    monkeypatch.setenv("WATCHSKILL_OFFLINE", "1")

    with patch("watch_skill.update_check.get_update_cache_path", return_value=cache_file):
        with patch("threading.Thread") as mock_thread:
            check_for_updates()
            mock_thread.assert_not_called()


def test_check_for_updates_emits_to_stderr_never_stdout(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    cache_file = tmp_path / "update-check.json"
    cache_data = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "latest_version": "9.9.9",
        "release_url": "https://github.com/codevcn/watch-skill/releases/tag/v9.9.9",
        "etag": "test",
        "last_notified_at": None,
        "last_notified_version": None,
    }
    _write_cache(cache_file, cache_data)

    monkeypatch.delenv("WATCHSKILL_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("WATCHSKILL_OFFLINE", raising=False)

    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    with patch("watch_skill.update_check.get_update_cache_path", return_value=cache_file):
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf):
            check_for_updates()

    # Stdout must remain 100% clean
    assert stdout_buf.getvalue() == ""
    # Stderr has the notification
    assert "[watch-skill] Update available:" in stderr_buf.getvalue()
    assert "9.9.9" in stderr_buf.getvalue()

    # Second call should not spam (rate-limited by last_notified_version)
    stderr_buf2 = io.StringIO()
    with patch("watch_skill.update_check.get_update_cache_path", return_value=cache_file):
        with patch("sys.stdout", stdout_buf), patch("sys.stderr", stderr_buf2):
            check_for_updates()
    assert stderr_buf2.getvalue() == ""


def test_fetch_latest_release_handles_errors_gracefully(tmp_path: Path):
    cache_file = tmp_path / "update-check.json"

    # Simulated network timeout / failure
    with patch("urllib.request.urlopen", side_effect=TimeoutError("Connection timed out")):
        _fetch_latest_release("codevcn/watch-skill", "1.5.3", cache_file, None)
    # File not created or crashed
    assert not cache_file.exists()


def test_fetch_latest_release_success(tmp_path: Path):
    cache_file = tmp_path / "update-check.json"

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.headers.get.return_value = "W/\"tag-1.6.0\""
    mock_resp.read.return_value = json.dumps({
        "tag_name": "v1.6.0",
        "html_url": "https://github.com/codevcn/watch-skill/releases/tag/v1.6.0",
    }).encode("utf-8")

    mock_urlopen = MagicMock()
    mock_urlopen.__enter__.return_value = mock_resp

    with patch("urllib.request.urlopen", return_value=mock_urlopen):
        _fetch_latest_release("codevcn/watch-skill", "1.5.3", cache_file, None)

    assert cache_file.exists()
    cached = _read_cache(cache_file)
    assert cached is not None
    assert cached["latest_version"] == "1.6.0"
    assert cached["etag"] == "W/\"tag-1.6.0\""


def test_cli_runner_stdout_json_purity_with_update(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    from typer.testing import CliRunner

    from watch_skill.surfaces.cli.main import app

    cache_file = tmp_path / "update-check.json"
    cache_data = {
        "schema_version": SCHEMA_VERSION,
        "checked_at": datetime.now(UTC).isoformat(),
        "latest_version": "9.9.9",
        "release_url": "https://github.com/codevcn/watch-skill/releases/tag/v9.9.9",
        "etag": "test",
        "last_notified_at": None,
        "last_notified_version": None,
    }
    _write_cache(cache_file, cache_data)

    monkeypatch.delenv("WATCHSKILL_NO_UPDATE_CHECK", raising=False)
    monkeypatch.delenv("WATCHSKILL_OFFLINE", raising=False)

    runner = CliRunner()
    with patch("watch_skill.update_check.get_update_cache_path", return_value=cache_file):
        # Even with update available, `version` output on stdout must be clean version string
        from watch_skill import __version__
        result = runner.invoke(app, ["version"])
        assert result.exit_code == 0
        assert result.stdout.strip() == __version__

