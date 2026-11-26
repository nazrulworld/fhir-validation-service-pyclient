"""SDK-built validate requests and fixture responses match the pinned contract (T035)."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest

from fvs_client import Client, IgRef, ResultFormat
from tests.conftest import MockRouter
from tests.contract._openapi import check_request, check_response
from tests.fixtures import load


@pytest.fixture
def capture(mock_router: MockRouter) -> Iterator[tuple[Client, MockRouter]]:
    mock_router.add(
        "POST",
        "/R4/validate",
        content=load("validation/patient_valid.json"),
        content_type="application/json",
    )
    http = httpx.Client(transport=mock_router.transport())
    with Client("http://localhost:8880", api_key="k", http_client=http) as c:
        yield c, mock_router
    http.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"ig": "hl7.fhir.uv.ips#1.1.0"},
        {"ig": (IgRef("a", "1.0.0"), IgRef("b", "2.0.0"))},
        {"profiles": ["http://hl7.org/fhir/StructureDefinition/Patient"]},
        {"tx": "https://tx.fhir.org/r4", "tx_mode": "server"},
        {"tx_mode": "none"},
        {"result_format": ResultFormat.OPERATION_OUTCOME_JSON},
        {"result_format": ResultFormat.OPERATION_OUTCOME_XML},
    ],
)
def test_json_requests_match_contract(
    capture: tuple[Client, MockRouter], kwargs: dict[str, Any]
) -> None:
    client, router = capture
    client.validate({"resourceType": "Patient"}, fhir_version="R4", raw=True, **kwargs)
    check_request(router.last)


def test_xml_request_matches_contract(capture: tuple[Client, MockRouter]) -> None:
    client, router = capture
    client.validate('<Patient xmlns="http://hl7.org/fhir"/>', fhir_version="R4", raw=True)
    assert router.last.headers["content-type"] == "application/fhir+xml"
    check_request(router.last)


REQUEST = httpx.Request(
    "POST",
    "http://localhost:8880/R4/validate",
    headers={"Authorization": "Bearer k", "Content-Type": "application/fhir+json"},
    content=b'{"resourceType":"Patient"}',
)


@pytest.mark.parametrize(
    "fixture", ["validation/patient_valid.json", "validation/patient_invalid.json"]
)
def test_summary_fixtures_match_contract(fixture: str) -> None:
    check_response(REQUEST, 200, load(fixture), "application/json")


def test_operation_outcome_fixture_matches_contract() -> None:
    check_response(REQUEST, 200, load("validation/operation_outcome.json"), "application/fhir+json")


@pytest.mark.parametrize(
    ("status", "problem"),
    [
        (400, "invalid-request"),
        (400, "invalid-resource"),
        (400, "unknown-profile"),
        (401, "unauthorized"),
        (403, "forbidden"),
        (404, "package-not-found"),
        (424, "dependency-not-found"),
        (429, "rate-limited"),
        (503, "not-ready"),
    ],
)
def test_problem_fixtures_match_contract(status: int, problem: str) -> None:
    check_response(REQUEST, status, load(f"problems/{problem}.json"), "application/problem+json")
