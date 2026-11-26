"""SC-004: SDK overhead per validate() call stays under 5 ms for a ~90 KB resource (T090).

Opt-in: ``uv run pytest -m perf tests/perf``. The transport answers instantly from memory, so
the measured time is the SDK's own work: option checks, JSON encoding, request building,
header/response parsing and model construction.
"""

from __future__ import annotations

import statistics
import time

import httpx
import pytest

from fvs_client import Client
from tests.fixtures import load

pytestmark = pytest.mark.perf

BODY = load("validation/patient_invalid.json")
CALLS = 500
BUDGET_SECONDS = 0.005


def _resource() -> dict[str, object]:
    names = [{"family": f"Family{i}", "given": [f"Given{i}", "Middle"]} for i in range(1650)]
    return {"resourceType": "Patient", "id": "perf", "active": True, "name": names}


def test_validate_overhead_under_5ms() -> None:
    resource = _resource()
    size = len(httpx.Request("POST", "http://x", json=resource).content)
    assert 80_000 <= size <= 100_000, size

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=BODY,
            headers={"content-type": "application/json", "x-validation-context": "base"},
        )

    with (
        httpx.Client(transport=httpx.MockTransport(handler)) as http,
        Client("https://fvs.test", api_key="k", http_client=http) as client,
    ):
        for _ in range(20):  # warm-up
            client.validate(resource, fhir_version="R4")
        samples = []
        for _ in range(CALLS):
            start = time.perf_counter()
            client.validate(resource, fhir_version="R4")
            samples.append(time.perf_counter() - start)
    median = statistics.median(samples)
    print(f"median {median * 1000:.2f} ms, p95 {sorted(samples)[int(CALLS * 0.95)] * 1000:.2f} ms")
    assert median < BUDGET_SECONDS
