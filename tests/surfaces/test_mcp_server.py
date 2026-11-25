"""MCP server end-to-end via the in-process FastMCP client (stdio semantics)."""
from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("fastmcp", reason="mcp extra not installed")
pytest.importorskip("scenedetect", reason="perceive extra not installed")

from fastmcp import Client  # noqa: E402

from watch_skill.surfaces.mcp.server import mcp  # noqa: E402


def _call(tool: str, **kwargs):
    async def _run():
        async with Client(mcp) as client:
            return await client.call_tool(tool, kwargs)

    return asyncio.run(_run())


def test_tools_are_registered() -> None:
    async def _list():
        async with Client(mcp) as client:
            return {t.name for t in await client.list_tools()}

    names = asyncio.run(_list())
    assert {"watch_video", "ask_video", "get_moment", "search_videos", "list_videos", "doctor"} <= names
    # the loop family: v0.6 names unchanged (compat contract) + v0.7 loop types
    assert {"loop_start", "loop_iterate", "loop_status"} <= names
    assert {"loop_video_gen", "loop_game", "loop_monitor"} <= names
    assert {"extract_chapters", "extract_bug_report", "analyze_hook"} <= names
    # v1.0 library layer
    assert {"library_synthesize", "library_overview"} <= names


def test_docs_state_the_real_tool_count() -> None:
    """Docs quoted "13 MCP tools" for three releases after the count changed.

    Nothing failed when a tool was added, so the number silently rotted in
    several pages at once. Pin the documented figure to the registry instead
    of to someone's memory.

    The pattern allows adjectives between the count and "tools". Matching only
    "N tools" and "N MCP tools" let "23 public tools" and "the other 25 tools"
    stay stale while this test passed. Files are enumerated rather than
    globbed, because a changelog entry describing an older release is correct
    at its own number.
    """
    import re
    from pathlib import Path

    async def _list():
        async with Client(mcp) as client:
            return [t.name for t in await client.list_tools()]

    count = len(asyncio.run(_list()))
    root = Path(__file__).resolve().parents[2]
    pattern = re.compile(r"(\d+)(?:\s+[A-Za-z]+){0,2}\s+tools\b")

    stale: list[str] = []
    for rel in ("README.md", "docs/getting-started.md", "docs/architecture.md",
                "docs/README.md", "docs/tools/README.md", "SECURITY.md",
                "docs/agents/windsurf.md", "templates/agent-integration/AGENTS.example.md",
                "examples/06-agent-integration/README.md", "llms.txt"):
        path = root / rel
        if not path.is_file():
            continue
        for found in pattern.findall(path.read_text(encoding="utf-8")):
            if int(found) != count:
                stale.append(f"{rel} says {found}")

    assert not stale, f"registry has {count} tools; {'; '.join(stale)}"


def test_list_videos_empty() -> None:
    result = _call("list_videos")
    assert "empty" in result.content[0].text


def test_watch_then_ask_roundtrip(sample_video: Path) -> None:
    result = _call(
        "watch_video", source=str(sample_video), question="what colors appear?", budget=8
    )
    text = result.content[0].text
    assert "video_id:" in text
    assert "# watch-skill: video report" in text
    images = [c for c in result.content if c.type == "image"]
    assert images, "watch_video returned no image blocks"

    listing = _call("list_videos")
    assert "sample clip.mp4" in listing.content[0].text or "Indexed videos" in listing.content[0].text

    asked = _call("ask_video", video=str(sample_video), question="what happens first?")
    asked_text = asked.content[0].text
    assert "confidence:" in asked_text
    assert "tokens saved" in asked_text


def test_get_moment_after_watch(sample_video: Path) -> None:
    _call("watch_video", source=str(sample_video), budget=8)
    result = _call("get_moment", video=str(sample_video), timestamp="0:06", window=4.0)
    text = result.content[0].text
    assert "Moment 00:06" in text
    images = [c for c in result.content if c.type == "image"]
    assert images


def test_ask_unknown_video_returns_structured_error() -> None:
    result = _call("ask_video", video="never-indexed", question="anything")
    assert "index.video_not_found" in result.content[0].text


def test_server_source_has_no_mojibake() -> None:
    """Regression: the rebrand rewrite mangled '—'/'±' into mojibake
    ('â€”', 'آ±') inside the server instructions and tool output strings."""
    from watch_skill.surfaces.mcp import server as server_mod

    source = Path(server_mod.__file__).read_text(encoding="utf-8")
    for bad in ("â€", "آ±", "Â±"):
        assert bad not in source, f"mojibake {bad!r} in server.py"


def test_frame_cap_respected(sample_video: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WATCHSKILL_RESPONSE_FRAME_CAP", "3")
    from watch_skill.config import reset_settings

    reset_settings()
    result = _call("watch_video", source=str(sample_video), budget=10)
    images = [c for c in result.content if c.type == "image"]
    assert len(images) <= 3


def test_the_tool_reference_documents_every_tool() -> None:
    """The reference opened with "All 37 tools" and documented 35.

    The count guard above only compares numbers, so a page can state the right
    total and still omit the tools it promises. This checks the headings
    against the registry instead.
    """
    import re
    from pathlib import Path

    async def _list():
        async with Client(mcp) as client:
            return {t.name for t in await client.list_tools()}

    registered = asyncio.run(_list())
    doc = (Path(__file__).resolve().parents[2] / "docs" / "tools" / "README.md")
    headings = set(re.findall(r"^#{2,4}\s+`?([a-z_]+)`?", doc.read_text(encoding="utf-8"), re.M))
    assert not registered - headings, (
        f"tools with no section in docs/tools/README.md: {sorted(registered - headings)}")


def test_the_handshake_reports_watch_skills_version_not_the_frameworks() -> None:
    """A client asking what it is connected to must be told about this server.

    FastMCP defaults `version` to its own, so the initialize handshake reported
    the framework's version — an MCP client, and anyone reading a bug report
    from one, saw 3.4.7 for a 1.3.0rc2 server. The registry entry declares the
    package version too, and the two disagreeing sends support conversations
    to the wrong place.
    """
    from watch_skill import __version__

    assert mcp.version == __version__


def _unwrap_error(res) -> dict[str, object]:
    import json

    parsed = json.loads(res.content[0].text)
    if isinstance(parsed, list):
        return json.loads(parsed[0])
    return parsed


def test_watch_video_forwards_quality_options_and_validates_times(
    monkeypatch,
) -> None:
    """watch_video passes resolution/timestamps/transcript_only/cloud_stt and validates times."""
    from types import SimpleNamespace

    captured: dict[str, object] = {}

    def _fake_watch(source: str, **kwargs):
        captured["source"] = source
        captured.update(kwargs)
        return SimpleNamespace(perception=SimpleNamespace(frames=[]))

    monkeypatch.setattr("watch_skill.watch.watch", _fake_watch)
    monkeypatch.setattr("watch_skill.index.index_watch_result", lambda _r: "vid-quality")
    monkeypatch.setattr("watch_skill.report.render_report", lambda _r: "report ok")

    ok_res = _call(
        "watch_video",
        source="demo.mp4",
        start="00:05",
        end="00:20",
        resolution=1024,
        timestamps="00:08, 00:12",
        transcript_only=True,
        cloud_stt=True,
    )
    ok_text = ok_res.content[0].text
    assert "video_id: vid-quality" in ok_text
    assert "report ok" in ok_text
    assert captured["source"] == "demo.mp4"
    assert captured["start_seconds"] == 5.0
    assert captured["end_seconds"] == 20.0
    assert captured["frame_width"] == 1024
    assert captured["cue_timestamps"] == [8.0, 12.0]
    assert captured["transcript_only"] is True
    assert captured["allow_cloud_stt"] is True

    bad_payload = _unwrap_error(
        _call("watch_video", source="demo.mp4", timestamps="not-a-timestamp")
    )
    assert bad_payload["error"] == "perceive.bad_window"
    assert bad_payload["fix"]


def test_get_moment_forwards_max_frames_and_returns_structured_errors(
    monkeypatch,
) -> None:
    """get_moment forwards max_frames and maps bad inputs to structured error JSON."""
    from types import SimpleNamespace

    seen: dict[str, object] = {}

    def _fake_moment(
        video: str,
        timestamp: float,
        window: float = 10.0,
        *,
        max_frames: int = 6,
    ):
        seen["video"] = video
        seen["timestamp"] = timestamp
        seen["window"] = window
        seen["max_frames"] = max_frames
        return SimpleNamespace(
            video_id=video,
            timestamp=timestamp,
            window=window,
            segments=[],
            ocr=[],
            frames=[],
        )

    monkeypatch.setattr("watch_skill.index.get_moment", _fake_moment)

    ok_res = _call("get_moment", video="vid-1", timestamp="01:10", window=8.0, max_frames=9)
    assert "Moment 01:10" in ok_res.content[0].text
    assert seen == {
        "video": "vid-1",
        "timestamp": 70.0,
        "window": 8.0,
        "max_frames": 9,
    }

    bad_ts = _unwrap_error(_call("get_moment", video="vid-1", timestamp="bad-time"))
    assert bad_ts["error"] == "index.invalid_timestamp"
    assert bad_ts["fix"]

    bad_mf = _unwrap_error(
        _call("get_moment", video="vid-1", timestamp="10", max_frames=99)
    )
    assert bad_mf["error"] == "index.invalid_max_frames"
    assert bad_mf["fix"]

