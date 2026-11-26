"""The vendored service contract must be byte-identical to the pinned upstream v1.0.0 snapshot."""

import hashlib
from pathlib import Path

SNAPSHOT = Path(__file__).with_name("fvs-openapi-v1.0.0.yaml")
EXPECTED_SHA256 = "a4bfd8b09c848b398bb0f623f03a5a99b5d3abc5277af842cee111e7d42cfabe"


def test_snapshot_is_pinned() -> None:
    assert hashlib.sha256(SNAPSHOT.read_bytes()).hexdigest() == EXPECTED_SHA256
