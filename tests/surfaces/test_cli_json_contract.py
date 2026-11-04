"""Tests ensuring all CLI commands satisfy the pure JSON contract and schema 1.0."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

from typer.testing import CliRunner

from watch_skill.errors import AcquisitionError, IndexError_
from watch_skill.surfaces.cli.main import app

runner = CliRunner()


def assert_pure_json_envelope(stdout: str, expected_command: str) -> dict:
    stripped = stdout.strip()
    assert stripped.startswith("{") and stripped.endswith("}"), f"Stdout is not a pure JSON object: {stdout}"
    data = json.loads(stripped)
    assert data["schema_version"] == "1.0"
    assert data["command"] == expected_command
    assert "ok" in data
    assert "data" in data
    assert "error" in data
    return data


class TestListJsonContract:
    def test_list_json_success(self) -> None:
        mock_videos = [
            {
                "id": "test_vid_1",
                "source": "https://example.com/v.mp4",
                "duration_seconds": 60.0,
                "title": "Test Video 1",
            }
        ]
        with patch("watch_skill.index.list_videos", return_value=mock_videos):
            res = runner.invoke(app, ["list", "--json"])
            assert res.exit_code == 0
            payload = assert_pure_json_envelope(res.stdout, "list")
            assert payload["ok"] is True
            assert len(payload["data"]["items"]) == 1
            assert payload["data"]["items"][0]["id"] == "test_vid_1"

    def test_list_json_failure(self) -> None:
        with patch(
            "watch_skill.index.list_videos",
            side_effect=IndexError_("Database locked", code="index.locked", fix="Retry after process exits."),
        ):
            res = runner.invoke(app, ["list", "--json"])
            assert res.exit_code != 0
            payload = assert_pure_json_envelope(res.stdout, "list")
            assert payload["ok"] is False
            assert payload["error"]["code"] == "index.locked"
            assert payload["error"]["fix"] == "Retry after process exits."


class TestSearchJsonContract:
    def test_search_json_success(self) -> None:
        mock_groups = [
            {
                "video_id": "vid_search_1",
                "hits": [
                    {
                        "timestamp": 12.5,
                        "text": "test phrase found",
                        "kind": "transcript",
                        "score": 0.95,
                    }
                ],
            }
        ]
        with patch("watch_skill.index.search_videos", return_value=mock_groups):
            res = runner.invoke(app, ["search", "test phrase", "--json"])
            assert res.exit_code == 0
            payload = assert_pure_json_envelope(res.stdout, "search")
            assert payload["ok"] is True
            assert payload["data"]["query"] == "test phrase"
            assert len(payload["data"]["items"]) == 1
            assert payload["data"]["items"][0]["video_id"] == "vid_search_1"

    def test_search_json_error(self) -> None:
        with patch(
            "watch_skill.index.search_videos",
            side_effect=IndexError_("Corrupted index database", code="index.corrupt", fix="Re-index video."),
        ):
            res = runner.invoke(app, ["search", "query", "--json"])
            assert res.exit_code != 0
            payload = assert_pure_json_envelope(res.stdout, "search")
            assert payload["ok"] is False
            assert payload["error"]["code"] == "index.corrupt"
            assert payload["error"]["fix"] == "Re-index video."


class TestAskJsonContract:
    def test_ask_json_success(self, tmp_path) -> None:
        fake_frame = tmp_path / "frame_ans.jpg"
        fake_frame.write_text("frame data")

        mock_answer = MagicMock()
        mock_answer.text = "The answer is 42."
        mock_answer.confidence = 0.88
        mock_answer.frames = [str(fake_frame)]
        mock_answer.evidence = [{"type": "ocr", "text": "42"}]
        mock_answer.cached = False
        mock_answer.verified = True
        mock_answer.escalations_used = []
        mock_answer.budget_stopped = False
        mock_answer.deadline_stopped = False
        mock_answer.tokens_saved_estimate = 1200

        with patch("watch_skill.answer.answer_question", return_value=mock_answer):
            res = runner.invoke(app, ["ask", "vid_123", "What is the answer?", "--json"])
            assert res.exit_code == 0
            payload = assert_pure_json_envelope(res.stdout, "ask")
            assert payload["ok"] is True
            assert payload["video_id"] == "vid_123"
            assert payload["answer"] == "The answer is 42."
            assert payload["confidence"] == 0.88
            assert payload["frame_paths"] == [str(fake_frame.resolve())]

    def test_ask_json_not_found(self) -> None:
        with patch(
            "watch_skill.answer.answer_question",
            side_effect=IndexError_("Video 'absent' not in index", code="index.video_not_found", fix="Watch it first."),
        ):
            res = runner.invoke(app, ["ask", "absent", "Where is it?", "--json"])
            assert res.exit_code != 0
            payload = assert_pure_json_envelope(res.stdout, "ask")
            assert payload["ok"] is False
            assert payload["error"]["code"] == "index.video_not_found"
            assert payload["error"]["fix"] == "Watch it first."


class TestWatchJsonContract:
    def test_watch_json_success(self, tmp_path) -> None:
        fake_frame = tmp_path / "f_0.jpg"
        fake_frame.write_text("img")

        mock_frame = MagicMock()
        mock_frame.path = str(fake_frame)
        mock_frame.timestamp = 10.0
        mock_frame.ocr_text = []

        mock_seg = MagicMock()
        mock_seg.start = 0.0
        mock_seg.end = 5.0
        mock_seg.text = "hello"

        mock_watch_result = MagicMock()
        mock_watch_result.video_id = "v_watched_99"
        mock_watch_result.source = "https://example.com/stream.m3u8"
        mock_watch_result.duration = 45.0
        mock_watch_result.perception = MagicMock()
        mock_watch_result.perception.frames = [mock_frame]
        mock_watch_result.transcript = MagicMock()
        mock_watch_result.transcript.segments = [mock_seg]

        with (
            patch("watch_skill.watch.watch", return_value=mock_watch_result),
            patch("watch_skill.index.index_watch_result", return_value="v_watched_99"),
        ):
            res = runner.invoke(app, ["watch", "https://example.com/stream.m3u8", "--json"])
            assert res.exit_code == 0
            payload = assert_pure_json_envelope(res.stdout, "watch")
            assert payload["ok"] is True
            assert payload["video_id"] == "v_watched_99"
            assert payload["frame_paths"] == [str(fake_frame.resolve())]

    def test_watch_json_failure(self) -> None:
        with patch(
            "watch_skill.watch.watch",
            side_effect=AcquisitionError(
                "Source unreachable", code="acquire.failed", fix="Check video URL."
            ),
        ):
            res = runner.invoke(app, ["watch", "https://invalid.example/video.mp4", "--json"])
            assert res.exit_code != 0
            payload = assert_pure_json_envelope(res.stdout, "watch")
            assert payload["ok"] is False
            assert payload["error"]["code"] == "acquire.failed"
            assert payload["error"]["fix"] == "Check video URL."


class TestMomentJsonContract:
    def test_moment_json_invalid_window(self) -> None:
        res = runner.invoke(app, ["moment", "v123", "10.0", "--window", "0.1", "--json"])
        assert res.exit_code != 0
        payload = assert_pure_json_envelope(res.stdout, "moment")
        assert payload["ok"] is False
        assert payload["error"]["code"] == "index.invalid_window"
        assert "0.5 and 120.0" in payload["error"]["message"]

    def test_moment_json_invalid_timestamp(self) -> None:
        res = runner.invoke(app, ["moment", "v123", "bad:ts:99", "--json"])
        assert res.exit_code != 0
        payload = assert_pure_json_envelope(res.stdout, "moment")
        assert payload["ok"] is False
        assert payload["error"]["code"] == "index.invalid_timestamp"
