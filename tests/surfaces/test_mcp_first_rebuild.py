"""Regression tests for the MCP-first rebuild and bug fixes."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from typer.testing import CliRunner


def test_parse_watch_times_and_moment_args_raise_structured_errors() -> None:
    from watch_skill.errors import IndexError_, PerceptionError
    from watch_skill.perceive.budget import parse_moment_args, parse_watch_times

    start, end, cues = parse_watch_times("00:05", "12.5", "00:07, 00:10")
    assert start == 5.0
    assert end == 12.5
    assert cues == [7.0, 10.0]

    with pytest.raises(PerceptionError) as bad_start:
        parse_watch_times("xyz", None, None)
    assert bad_start.value.code == "perceive.bad_window"
    assert bad_start.value.fix

    with pytest.raises(PerceptionError) as bad_cues:
        parse_watch_times(None, None, "00:05, nope")
    assert bad_cues.value.code == "perceive.bad_window"
    assert bad_cues.value.fix

    ts, win = parse_moment_args("01:02", 15.0)
    assert (ts, win) == (62.0, 15.0)

    with pytest.raises(IndexError_) as bad_win:
        parse_moment_args("10", 0.1)
    assert bad_win.value.code == "index.invalid_window"
    assert bad_win.value.fix

    with pytest.raises(IndexError_) as bad_ts:
        parse_moment_args("not-a-ts", 10.0)
    assert bad_ts.value.code == "index.invalid_timestamp"
    assert bad_ts.value.fix


def test_watch_job_forwards_quality_options(monkeypatch: pytest.MonkeyPatch) -> None:
    from watch_skill.jobs import handlers

    captured: dict[str, object] = {}

    def _fake_watch(source: str, **kwargs):
        captured["source"] = source
        captured.update(kwargs)
        return SimpleNamespace(perception=SimpleNamespace(frames=[]))

    monkeypatch.setattr("watch_skill.watch.watch", _fake_watch)
    monkeypatch.setattr("watch_skill.index.store.index_watch_result", lambda _r: "job-vid")

    ctx = handlers.JobContext(
        job=SimpleNamespace(
            job_id="job-1",
            payload={
                "source": "clip.mp4",
                "start": "00:03",
                "end": "00:15",
                "budget": 24,
                "resolution": 1024,
                "timestamps": "00:06, 00:09",
                "transcript_only": True,
                "cloud_stt": True,
            },
        ),
        owner="worker-1",
        _heartbeat=lambda *a, **kw: True,
        _cancel_requested=lambda _id: False,
    )
    ref_id, ref_kind = handlers._watch_job(ctx)
    assert (ref_id, ref_kind) == ("job-vid", "video_id")
    assert captured["source"] == "clip.mp4"
    assert captured["start_seconds"] == 3.0
    assert captured["end_seconds"] == 15.0
    assert captured["max_frames"] == 24
    assert captured["frame_width"] == 1024
    assert captured["cue_timestamps"] == [6.0, 9.0]
    assert captured["transcript_only"] is True
    assert captured["allow_cloud_stt"] is True


def test_frozen_server_command_and_antigravity_detection(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    from watch_skill.health import agents_setup

    fake_exe = tmp_path / "Program Files" / "Watch Skill" / "watch-skill.exe"
    fake_exe.parent.mkdir(parents=True)
    fake_exe.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(fake_exe))
    monkeypatch.setattr(agents_setup.shutil, "which", lambda _name: None)

    cmd, args = agents_setup.server_command()
    assert cmd == str(fake_exe.resolve())
    assert args == ["serve"]

    home = tmp_path / "home"
    (home / ".gemini" / "antigravity").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", lambda: home)

    targets = {target.key: target for target in agents_setup.detect_agents()}
    assert "antigravity" in targets
    ag = targets["antigravity"]
    assert ag.detected is True
    assert ag.configured is False

    agents_setup.configure_agent(ag)
    written = json.loads(ag.config_path.read_text(encoding="utf-8"))
    assert written["mcpServers"]["watch-skill"]["command"] == str(fake_exe.resolve())
    assert written["mcpServers"]["watch-skill"]["args"] == ["serve"]

    targets_after = {target.key: target for target in agents_setup.detect_agents()}
    assert targets_after["antigravity"].configured is True


def test_embeddings_offline_respects_local_files_only_without_latching(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import types

    from watch_skill.index import embeddings
    from watch_skill.policy import ExecutionPolicy, use_policy

    embeddings.release_models()
    monkeypatch.setattr(embeddings, "_unavailable", False)

    calls: list[dict[str, object]] = []

    class _FakeTextEmbedding:
        def __init__(self, model_name: str, **kwargs):
            calls.append({"model_name": model_name, **kwargs})
            if kwargs.get("local_files_only"):
                raise OSError("not cached locally")

    monkeypatch.setitem(
        sys.modules,
        "fastembed",
        types.SimpleNamespace(TextEmbedding=_FakeTextEmbedding),
    )

    with use_policy(ExecutionPolicy(offline=True)):
        assert embeddings._get_model("BAAI/bge-small-en-v1.5") is None
    assert calls and calls[0].get("local_files_only") is True
    assert embeddings._unavailable is False

    with use_policy(ExecutionPolicy(offline=False)):
        model = embeddings._get_model("BAAI/bge-small-en-v1.5")
    assert model is not None
    assert calls[1].get("local_files_only") is False
    embeddings.release_models()


def test_cli_skips_update_check_on_serve_bridge_and_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from watch_skill.surfaces.cli import main as cli_main

    runner = CliRunner()
    check_calls: list[bool] = []

    def _fake_check() -> None:
        check_calls.append(True)
        return None

    monkeypatch.setattr("watch_skill.update_check.check_for_updates", _fake_check)
    monkeypatch.setattr("watch_skill.surfaces.mcp.server.main", lambda **_kw: None)

    res_serve = runner.invoke(cli_main.app, ["serve"])
    assert res_serve.exit_code == 0, res_serve.output
    assert check_calls == []

    for sub in ("serve", "bridge", "update"):
        cli_main._main(
            ctx=SimpleNamespace(invoked_subcommand=sub),
            _version=False,
        )
    assert check_calls == []

    res_cfg = runner.invoke(cli_main.app, ["config", "list"])
    assert res_cfg.exit_code == 0, res_cfg.output
    assert len(check_calls) == 1
