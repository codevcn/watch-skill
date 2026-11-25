"""Token-aware frame budgets — tiers inherited verbatim from the reference.

Budget-by-duration keeps short videos dense and long videos capped; focused
mode (user named a moment) spends more per second. Universal 2 fps rate cap.
"""
from __future__ import annotations

from watch_skill.config import get_settings


def _clamp(target: float, duration_seconds: float, max_frames: int) -> tuple[float, int]:
    max_fps = get_settings().max_fps
    fps = min(target / duration_seconds if duration_seconds > 0 else 1.0, max_fps)
    frames = min(max_frames, max(1, int(round(fps * duration_seconds))))
    return fps, frames


def flow_cues(duration_seconds: float, cap: int = 20) -> list[float]:
    """Evenly pinned timestamps across a SHORT recording (loop iterations,
    monitor samples). Cue frames are reserved against the cap and never
    deduped — which matters because phash is grayscale: a blue button
    turning gray or a total turning red is luminance-invisible, and dedup
    would collapse the whole flow to one frame (the flagship browser demo
    caught exactly that). Watching a flow means keeping the in-between."""
    if duration_seconds <= 0:
        return []
    count = min(cap, max(4, int(round(duration_seconds * 2))))  # ≤2 fps
    step = duration_seconds / count
    return [round(step * (i + 0.5), 2) for i in range(count)]


def full_budget(duration_seconds: float, max_frames: int | None = None) -> tuple[float, int]:
    """(fps, target_frames) for a full-video scan."""
    cap = max_frames if max_frames is not None else get_settings().frame_cap
    if duration_seconds <= 0:
        return 1.0, 1
    if duration_seconds <= 30:
        target = min(cap, max(12, int(round(duration_seconds))))
    elif duration_seconds <= 60:
        target = min(cap, 40)
    elif duration_seconds <= 180:
        target = min(cap, 60)
    elif duration_seconds <= 600:
        target = min(cap, 80)
    else:
        target = cap
    return _clamp(target, duration_seconds, cap)


def focused_budget(duration_seconds: float, max_frames: int | None = None) -> tuple[float, int]:
    """(fps, target_frames) for a user-focused window — denser per second."""
    cap = max_frames if max_frames is not None else get_settings().frame_cap
    if duration_seconds <= 0:
        return min(get_settings().max_fps, 2.0), 2
    if duration_seconds <= 5:
        target = min(cap, max(10, int(round(duration_seconds * 6))))
    elif duration_seconds <= 15:
        target = min(cap, max(30, int(round(duration_seconds * 4))))
    elif duration_seconds <= 30:
        target = min(cap, 60)
    elif duration_seconds <= 60:
        target = min(cap, 80)
    else:
        target = cap
    return _clamp(target, duration_seconds, cap)


def parse_time(value: str | float | int | None) -> float | None:
    """Parse SS, MM:SS, or HH:MM:SS (optional .ms) into seconds."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    parts = text.split(":")
    try:
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except ValueError:
        pass
    raise ValueError(f"cannot parse time value: {value!r} (expected SS, MM:SS, or HH:MM:SS)")


def format_time(seconds: float) -> str:
    """Render seconds as MM:SS or H:MM:SS."""
    total = int(round(seconds))
    hours, rem = divmod(total, 3600)
    minutes, sec = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{sec:02d}"
    return f"{minutes:02d}:{sec:02d}"


def parse_cue_timestamps(timestamps: str | None) -> list[float] | None:
    """Parse comma-separated cue timestamps into seconds, raising PerceptionError on bad input."""
    if not timestamps or not timestamps.strip():
        return None
    from watch_skill.errors import PerceptionError

    cues: list[float] = []
    for raw in timestamps.split(","):
        tok = raw.strip()
        if not tok:
            continue
        try:
            val = parse_time(tok)
        except ValueError as exc:
            raise PerceptionError(
                f"Cannot parse cue timestamp: '{tok}'",
                code="perceive.bad_window",
                fix="pass comma-separated timestamps as SS, MM:SS, or HH:MM:SS (e.g. 00:30,01:45)",
            ) from exc
        if val is not None:
            if val < 0:
                raise PerceptionError(
                    f"Cue timestamp must be non-negative: '{tok}'",
                    code="perceive.bad_window",
                    fix="pass non-negative timestamps as SS, MM:SS, or HH:MM:SS (e.g. 00:30,01:45)",
                )
            cues.append(val)
    return cues or None


def parse_watch_times(
    start: str | None,
    end: str | None,
    timestamps: str | None = None,
) -> tuple[float | None, float | None, list[float] | None]:
    """Parse optional watch window and cue timestamps into structured seconds."""
    from watch_skill.errors import PerceptionError

    parsed: list[float | None] = []
    for label, raw in (("start", start), ("end", end)):
        try:
            parsed.append(parse_time(raw))
        except ValueError as exc:
            raise PerceptionError(
                f"Cannot parse {label} timestamp: '{raw}'",
                code="perceive.bad_window",
                fix=f"pass {label} as SS, MM:SS, or HH:MM:SS (e.g. 01:30)",
            ) from exc
    return parsed[0], parsed[1], parse_cue_timestamps(timestamps)


def parse_moment_args(timestamp: str, window: float) -> tuple[float, float]:
    """Validate and parse moment center timestamp and window across CLI/MCP/REST."""
    from watch_skill.errors import IndexError_

    if window < 0.5 or window > 120.0:
        raise IndexError_(
            "Window must be between 0.5 and 120.0 seconds.",
            code="index.invalid_window",
            fix="pass a window between 0.5 and 120.0 seconds (e.g. --window 10.0)",
        )
    try:
        ts = parse_time(timestamp)
    except ValueError:
        ts = None
    if ts is None or ts < 0:
        raise IndexError_(
            f"Cannot parse timestamp: '{timestamp}'",
            code="index.invalid_timestamp",
            fix="pass timestamp as SS, MM:SS, or HH:MM:SS (e.g. 02:30)",
        )
    return ts, float(window)
