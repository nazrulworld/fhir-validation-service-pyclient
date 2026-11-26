"""Test fixtures: response bodies taken from the pinned contract and the upstream wiki."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

FIXTURES = Path(__file__).parent


def load(path: str) -> bytes:
    """Return the raw bytes of ``tests/fixtures/<path>``."""
    return (FIXTURES / path).read_bytes()


def load_json(path: str) -> Any:
    """Return the decoded JSON of ``tests/fixtures/<path>``."""
    return json.loads(load(path))


def problem_names() -> list[str]:
    """Short names of every problem fixture, sorted."""
    return sorted(p.stem for p in (FIXTURES / "problems").glob("*.json"))
