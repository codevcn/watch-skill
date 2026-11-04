"""Tests for CLI moment command."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from watch_skill.errors import IndexError_
from watch_skill.surfaces.cli.main import app

runner = CliRunner()


def test_moment_invalid_window_json() -> None:
    res = runner.invoke(app, ["moment", "test_video", "10.0", "--window", "0.1", "--json"])
    assert res.exit_code != 0
    payload = json.loads(res.stdout)
    assert payload["ok"] is False
    assert payload["command"] == "moment"
    assert "Window must be between 0.5 and 120.0 seconds" in payload["error"]["message"]


def test_moment_window_too_large_json() -> None:
    res = runner.invoke(app, ["moment", "test_video", "10.0", "--window", "150.0", "--json"])
    assert res.exit_code != 0
    payload = json.loads(res.stdout)
    assert payload["ok"] is False
    assert "Window must be between 0.5 and 120.0 seconds" in payload["error"]["message"]


def test_moment_invalid_timestamp_json() -> None:
    res = runner.invoke(app, ["moment", "test_video", "invalid:time:format:99", "--json"])
    assert res.exit_code != 0
    payload = json.loads(res.stdout)
    assert payload["ok"] is False
    assert "Cannot parse timestamp" in payload["error"]["message"]


def test_moment_success_json(tmp_path) -> None:
    fake_frame = tmp_path / "frame_001.jpg"
    fake_frame.write_text("dummy")

    mock_ctx = MagicMock()
    mock_ctx.video_id = "abc12345"
    mock_ctx.timestamp = 15.0
    mock_ctx.window = 6.0
    mock_ctx.segments = [{"start": 14.0, "end": 16.0, "text": "hello world"}]
    mock_ctx.ocr = [{"timestamp": 15.0, "text": "ON SCREEN"}]
    mock_ctx.frames = [{"timestamp": 15.0, "frame_path": str(fake_frame)}]

    with patch("watch_skill.index.get_moment", return_value=mock_ctx):
        res = runner.invoke(app, ["moment", "abc12345", "15.0", "--window", "6.0", "--json"])
        assert res.exit_code == 0
        payload = json.loads(res.stdout)
        assert payload["schema_version"] == "1.0"
        assert payload["ok"] is True
        assert payload["command"] == "moment"
        assert payload["video_id"] == "abc12345"
        assert payload["frame_paths"] == [str(fake_frame.resolve())]
        assert payload["data"]["timestamp"] == 15.0
        assert payload["data"]["window"] == 6.0
        assert len(payload["data"]["segments"]) == 1
        assert len(payload["data"]["ocr"]) == 1


def test_moment_success_human(tmp_path) -> None:
    fake_frame = tmp_path / "frame_001.jpg"
    fake_frame.write_text("dummy")

    mock_ctx = MagicMock()
    mock_ctx.video_id = "abc12345"
    mock_ctx.timestamp = 15.0
    mock_ctx.window = 6.0
    mock_ctx.segments = [{"start": 14.0, "end": 16.0, "text": "hello world"}]
    mock_ctx.ocr = [{"timestamp": 15.0, "text": "ON SCREEN"}]
    mock_ctx.frames = [{"timestamp": 15.0, "frame_path": str(fake_frame)}]

    with patch("watch_skill.index.get_moment", return_value=mock_ctx):
        res = runner.invoke(app, ["moment", "abc12345", "15.0", "--window", "6.0"])
        assert res.exit_code == 0
        assert "# Moment" in res.stdout
        assert "hello world" in res.stdout
        assert "ON SCREEN" in res.stdout
        assert str(fake_frame.resolve()) in res.stdout


def test_moment_video_not_found_json() -> None:
    with patch(
        "watch_skill.index.get_moment",
        side_effect=IndexError_("Video 'nonexistent' not indexed.", code="index.not_found", fix="Run `watch-skill watch <source>` first."),
    ):
        res = runner.invoke(app, ["moment", "nonexistent", "10.0", "--json"])
        assert res.exit_code == 1
        payload = json.loads(res.stdout)
        assert payload["ok"] is False
        assert "Video 'nonexistent' not indexed" in payload["error"]["message"]
        assert payload["error"]["code"] == "index.not_found"
        assert "fix" in payload["error"]
