"""Checksum parsing and verification for release assets."""
from __future__ import annotations

import hashlib
from pathlib import Path


def parse_sha256sums(content: str) -> dict[str, str]:
    """Parse standard sha256sums content (hash  filename) into a mapping.

    Handles leading/trailing whitespace, tab or multi-space delimiters, and
    optional binary flag markers (*) before filenames.
    """
    mapping: dict[str, str] = {}
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Split hash from filename
        parts = line.split(None, 1)
        if len(parts) != 2:
            continue
        sha, filename = parts
        filename = filename.lstrip("*").strip()
        if len(sha) == 64 and filename:
            mapping[filename] = sha.lower()
    return mapping


def compute_file_sha256(path: Path) -> str:
    """Compute lowercase hex SHA-256 digest of a file in 64KB blocks."""
    hasher = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest().lower()


def verify_file_sha256(path: Path, expected_sha256: str) -> bool:
    """Check if file matches expected SHA-256."""
    actual = compute_file_sha256(path)
    return actual.lower() == expected_sha256.strip().lower()
