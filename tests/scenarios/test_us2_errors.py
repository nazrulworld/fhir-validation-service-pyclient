"""US2 acceptance scenarios 1-6: errors and limits (T046).

Written against the ``client``/``make_client`` fixtures so they run on every client implementation.
"""

from __future__ import annotations

import httpx
import pytest

from fvs_client import (
    APIError,
    AuthenticationError,
    Client,
    DependencyConflictError,
    FVSConnectionError,
    FVSTimeoutError,
    InvalidResourceError,
    ProblemType,
    RateLimitError,
    RateLimitScope,
    ServerError,
    ServiceUnavailableError,
    TransportError,
    UnknownProfileError,
)
from tests.conftest import ClientFactory, MockRouter
from tests.fixtures import load, load_json, problem_names
from tests.unit.test_problems import EXPECTED_CLASS

PATIENT = {"resourceType": "Patient"}
PATH = "/R4/validate"


def _problem(router: MockRouter, name: str, headers: dict[str, str] | None = None) -> None:
    status = load_json(f"problems/{name}.json")["status"]
    router.add(
        "POST",
        PATH,
        status,
        content=load(f"problems/{name}.json"),
        content_type="application/problem+json",
        headers={"X-Request-Id": f"rid-{name}", **(headers or {})},
    )


@pytest.mark.parametrize("name", problem_names())
def test_every_problem_type_maps_to_its_error(
    name: str, make_client: ClientFactory, mock_router: MockRouter, sleeps: list[float]
) -> None:
    _problem(mock_router, name)
    client = make_client(retries=0)
    with pytest.raises(APIError) as info:
        client.validate(PATIENT, fhir_version="R4")
    err = info.value
    assert type(err) is EXPECTED_CLASS[name]
    assert err.status_code == load_json(f"problems/{name}.json")["status"]
    assert err.problem_type == ProblemType(name)
    assert err.request_id == f"rid-{name}"
    assert err.problem is not None
    assert err.problem.correlation_id == load_json(f"problems/{name}.json")["correlationId"]
    assert err.response.status_code == err.status_code
    assert sleeps == []


def test_1_bad_key_is_authentication_error_with_request_id(
    client: Client, mock_router: MockRouter
) -> None:
    _problem(mock_router, "unauthorized", {"WWW-Authenticate": "Bearer"})
    with pytest.raises(AuthenticationError) as info:
        client.validate(PATIENT, fhir_version="R4")
    assert info.value.request_id == "rid-unauthorized"
    assert "test-key" not in str(info.value)


def test_2_unknown_profile_lists_unresolved(client: Client, mock_router: MockRouter) -> None:
    _problem(mock_router, "unknown-profile")
    with pytest.raises(UnknownProfileError) as info:
        client.validate(
            PATIENT, fhir_version="R4", profiles=["http://example.org/StructureDefinition/nope"]
        )
    assert info.value.unresolved_profiles == ("http://example.org/StructureDefinition/nope",)


def test_problem_specific_fields(make_client: ClientFactory, mock_router: MockRouter) -> None:
    client = make_client(retries=0)
    _problem(mock_router, "invalid-resource")
    with pytest.raises(InvalidResourceError) as info1:
        client.validate("<Patient/>", fhir_version="R4")
    assert info1.value.issues[0].message.startswith("Unable to parse JSON")

    mock_router.routes.clear()
    _problem(mock_router, "dependency-conflict")
    with pytest.raises(DependencyConflictError) as info2:
        client.validate(PATIENT, fhir_version="R4")
    assert info2.value.conflicts == load_json("problems/dependency-conflict.json")["conflicts"]


def test_3_rate_limited_without_retry(make_client: ClientFactory, mock_router: MockRouter) -> None:
    _problem(
        mock_router,
        "rate-limited",
        {
            "Retry-After": "61",
            "RateLimit-Limit": "5",
            "RateLimit-Remaining": "0",
            "RateLimit-Reset": "61",
        },
    )
    client = make_client(retries=0)
    with pytest.raises(RateLimitError) as info:
        client.validate(PATIENT, fhir_version="R4")
    err = info.value
    assert err.scope is RateLimitScope.KEY
    assert err.limit == 5
    assert err.retry_after == 61
    assert err.meta.rate_limit.remaining == 0
    assert err.meta.attempts == 1


def test_4_retry_honours_retry_after_then_succeeds(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    _problem(mock_router, "rate-limited", {"Retry-After": "7"})
    mock_router.add(
        "POST", PATH, content=load("validation/patient_valid.json"), content_type="application/json"
    )
    result = client.validate(PATIENT, fhir_version="R4")
    assert result.valid is True
    assert sleeps == [7.0]
    assert result.meta.attempts == 2
    assert len(mock_router.requests) == 2


def test_4_retry_on_503_with_backoff_then_gives_up(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    _problem(mock_router, "overloaded")  # no Retry-After → backoff
    with pytest.raises(ServiceUnavailableError) as info:
        client.validate(PATIENT, fhir_version="R4")
    assert len(sleeps) == 2  # default max_retries=2
    assert all(0.0 <= s <= 8.0 for s in sleeps)
    assert info.value.meta.attempts == 3
    assert info.value.problem_type is ProblemType.OVERLOADED


def test_4_retry_after_over_cap_raises_at_once(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    _problem(mock_router, "rate-limited", {"Retry-After": "3600"})
    with pytest.raises(RateLimitError):
        client.validate(PATIENT, fhir_version="R4")
    assert sleeps == []


def test_4_retry_on_connect_error(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    mock_router.add("POST", PATH, exc=httpx.ConnectError("refused"))
    mock_router.add(
        "POST", PATH, content=load("validation/patient_valid.json"), content_type="application/json"
    )
    assert client.validate(PATIENT, fhir_version="R4").valid is True
    assert len(sleeps) == 1


def test_5_transport_errors_are_distinct(
    make_client: ClientFactory, mock_router: MockRouter, sleeps: list[float]
) -> None:
    mock_router.add("POST", PATH, exc=httpx.ConnectError("refused"))
    client = make_client()
    with pytest.raises(FVSConnectionError) as info:
        client.validate(PATIENT, fhir_version="R4")
    assert isinstance(info.value, TransportError)
    assert not isinstance(info.value, APIError)
    assert len(sleeps) == 2

    mock_router.routes.clear()
    mock_router.add("POST", PATH, exc=httpx.ReadTimeout("slow"))
    sleeps.clear()
    with pytest.raises(FVSTimeoutError):
        client.validate(PATIENT, fhir_version="R4")
    assert sleeps == []  # timeouts are never retried


def test_6_request_id_and_rate_limits_on_success_and_error(
    make_client: ClientFactory, mock_router: MockRouter
) -> None:
    rl = {"RateLimit-Limit": "30", "RateLimit-Remaining": "29", "RateLimit-Reset": "60"}
    mock_router.add(
        "POST",
        PATH,
        content=load("validation/patient_valid.json"),
        content_type="application/json",
        headers={"X-Request-Id": "ok-1", **rl},
    )
    client = make_client(retries=0)
    result = client.validate(PATIENT, fhir_version="R4")
    assert result.meta.request_id == "ok-1"
    assert (result.meta.rate_limit.limit, result.meta.rate_limit.remaining) == (30, 29)

    mock_router.routes.clear()
    _problem(mock_router, "package-not-found", rl)
    with pytest.raises(APIError) as info:
        client.validate(PATIENT, fhir_version="R4", ig="no.such.ig#1.0.0")
    assert info.value.request_id == "rid-package-not-found"
    assert info.value.meta.rate_limit.reset_seconds == 60


def test_non_problem_body_is_server_error(
    make_client: ClientFactory, mock_router: MockRouter
) -> None:
    mock_router.add("POST", PATH, 502, content="<html>Bad gateway</html>", content_type="text/html")
    with pytest.raises(ServerError) as info:
        make_client(retries=0).validate(PATIENT, fhir_version="R4")
    assert info.value.problem is None
    assert info.value.response.text == "<html>Bad gateway</html>"
    assert str(info.value).startswith("502 http-error: Bad Gateway")
