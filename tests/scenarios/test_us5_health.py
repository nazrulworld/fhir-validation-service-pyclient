"""US5 acceptance scenarios 1-3: check service health (T083)."""

from __future__ import annotations

import httpx
import pytest

from fvs_client import Client, FhirVersion, HealthStatus, RawResponse, ServiceUnavailableError
from fvs_client.models import AllowlistSource
from tests.conftest import ClientFactory, MockRouter
from tests.fixtures import load


def _serve(router: MockRouter, path: str, fixture: str, status: int = 200) -> None:
    router.add("GET", path, status, content=load(fixture), content_type="application/json")


def test_1_ready(client: Client, mock_router: MockRouter) -> None:
    _serve(mock_router, "/health/readiness", "health/readiness_up.json")
    report = client.health.readiness()
    assert report.is_ready
    assert "R4" in report.versions


def test_2_not_ready_is_returned_not_raised(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    _serve(mock_router, "/health/readiness", "health/readiness_down.json", 503)
    report = client.health.readiness()
    assert not report.is_ready
    assert "draining" in report.reasons
    assert report.meta.status_code == 503
    assert sleeps == []  # a report is an answer, not a reason to retry
    assert len(mock_router.requests) == 1

    _serve(mock_router, "/health", "health/health_down.json", 503)
    health = client.health.check()
    assert not health.is_healthy
    assert health.database.error == "connection refused"


def test_2_overloaded_503_problem_still_raises(
    make_client: ClientFactory, mock_router: MockRouter
) -> None:
    mock_router.add(
        "GET",
        "/health/readiness",
        503,
        content=load("problems/overloaded.json"),
        content_type="application/problem+json",
    )
    with pytest.raises(ServiceUnavailableError):
        make_client(retries=0).health.readiness()


def test_3_health_details(client: Client, mock_router: MockRouter) -> None:
    _serve(mock_router, "/health", "health/health_up.json")
    report = client.health.check()
    assert report.is_healthy
    assert report.database.status is HealthStatus.UP
    assert report.served_fhir_versions == (FhirVersion.R4, FhirVersion.R5)
    assert report.terminology_allowlist["R4"].source is AllowlistSource.REGISTRY
    assert report.acl_enabled is True


def test_liveness_and_raw(client: Client, mock_router: MockRouter) -> None:
    _serve(mock_router, "/health/liveness", "health/liveness.json")
    assert client.health.liveness().status is HealthStatus.UP
    raw = client.health.liveness(raw=True)
    assert isinstance(raw, RawResponse)
    assert raw.json()["status"] == "UP"


def test_no_api_key_needed(make_client: ClientFactory, mock_router: MockRouter) -> None:
    _serve(mock_router, "/health/liveness", "health/liveness.json")
    client = make_client(api_key=None)
    assert client.health.liveness().status is HealthStatus.UP
    assert "Authorization" not in mock_router.last.headers


def test_liveness_retried_on_connect_error(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    mock_router.add("GET", "/health/liveness", exc=httpx.ConnectError("refused"))
    _serve(mock_router, "/health/liveness", "health/liveness.json")
    assert client.health.liveness().status is HealthStatus.UP
    assert len(sleeps) == 1
