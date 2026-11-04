"""Agent-first JSON envelope for CLI commands.

Every command with --json outputs stdout containing ONLY one valid JSON document.
Progress bars, Rich output, warnings, and diagnostic logs go to stderr.
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class OutputEnvelope(BaseModel):
    """The canonical top-level envelope returned by all --json CLI commands."""

    schema_version: str = SCHEMA_VERSION
    ok: bool = True
    command: str
    video_id: str | None = None
    answer: str | None = None
    confidence: float | None = None
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    frame_paths: list[str] = Field(default_factory=list)
    data: dict[str, Any] = Field(default_factory=dict)
    error: dict[str, Any] | None = None


def clean_frame_paths(paths: list[str | Path]) -> list[str]:
    """Return deduplicated, normalized, absolute paths of existing frame files.

    Excludes paths inside PyInstaller _MEIPASS temporary directories.
    Preserves original sequence order.
    """
    seen: set[str] = set()
    cleaned: list[str] = []
    mei_prefix = getattr(sys, "_MEIPASS", None)
    mei_resolved = str(Path(mei_prefix).resolve()) if mei_prefix else None

    for p in paths:
        try:
            path_obj = Path(p).resolve()
            norm_str = str(path_obj)
            if mei_resolved and norm_str.startswith(mei_resolved):
                continue
            if path_obj.is_file() and norm_str not in seen:
                seen.add(norm_str)
                cleaned.append(norm_str)
        except OSError:
            continue
    return cleaned


def emit_json(envelope: OutputEnvelope) -> None:
    """Print the single canonical JSON document to stdout."""
    # Ensure stdout only contains clean json
    sys.stdout.write(envelope.model_dump_json(indent=2) + "\n")
    sys.stdout.flush()


def emit_json_error(
    command: str,
    code: str,
    message: str,
    fix: str | None = None,
    details: dict[str, Any] | None = None,
    video_id: str | None = None,
) -> None:
    """Print a structured JSON error envelope to stdout and flush."""
    env = OutputEnvelope(
        schema_version=SCHEMA_VERSION,
        ok=False,
        command=command,
        video_id=video_id,
        answer=None,
        confidence=None,
        evidence=[],
        frame_paths=[],
        data={},
        error={
            "code": code,
            "message": message,
            "fix": fix,
            "details": details or {},
        },
    )
    emit_json(env)
