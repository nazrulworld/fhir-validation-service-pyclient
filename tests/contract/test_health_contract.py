"""Health requests and fixture responses match the pinned contract (T082)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
import pytest

from fvs_client import Client
from tests.conftest import MockRouter
from tests.contract._openapi import check_request, check_response
from tests.fixtures import load

CASES: list[tuple[str, str, int, Callable[[Client], Any]]] = [
    ("/health", "health/health_up.json", 200, lambda c: c.health.check()),
    ("/health", "health/health_down.json", 503, lambda c: c.health.check()),
    ("/health/liveness", "health/liveness.json", 200, lambda c: c.health.liveness()),
    ("/health/readiness", "health/readiness_up.json", 200, lambda c: c.health.readiness()),
    ("/health/readiness", "health/readiness_down.json", 503, lambda c: c.health.readiness()),
]


@pytest.mark.parametrize(("path", "fixture", "status", "call"), CASES)
def test_health_matches_contract(
    mock_router: MockRouter, path: str, fixture: str, status: int, call: Callable[[Client], Any]
) -> None:
    mock_router.add("GET", path, status, content=load(fixture), content_type="application/json")
    with (
        httpx.Client(transport=mock_router.transport()) as http,
        Client("http://localhost:8880", http_client=http, retries=0) as c,
    ):
        call(c)
    check_request(mock_router.last)
    check_response(mock_router.last, status, load(fixture), "application/json")
