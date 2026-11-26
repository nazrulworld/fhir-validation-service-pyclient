"""US3: batch validation with bounded concurrency on both clients (T063)."""

from __future__ import annotations

import gc

import httpx
import pytest

from fvs_client import (
    AsyncClient,
    Client,
    FVSError,
    InputError,
    NotFoundError,
    OperationOutcomeResult,
    RateLimitError,
    RawResponse,
    ValidationResult,
)
from tests.conftest import ClientFactory, MockRouter
from tests.fixtures import load

PATH = "/R4/validate"


def _ok(router: MockRouter) -> None:
    router.add(
        "POST", PATH, content=load("validation/patient_valid.json"), content_type="application/json"
    )


def test_results_in_input_order_with_per_item_input_errors(
    client: Client, mock_router: MockRouter
) -> None:
    _ok(mock_router)
    resources: list[object] = [{"resourceType": "Patient", "id": str(i)} for i in range(100)]
    resources.append("not fhir")
    results = client.validate_many(resources, fhir_version="R4")  # type: ignore[arg-type]
    assert len(results) == 101
    assert all(isinstance(r, ValidationResult) for r in results[:100])
    assert isinstance(results[-1], InputError)
    sent_ids = sorted(
        int(r.content.split(b'"id":"')[1].split(b'"')[0]) for r in mock_router.requests
    )
    assert sent_ids == list(range(100))


def test_each_slot_holds_its_own_outcome(
    make_client: ClientFactory, mock_router: MockRouter
) -> None:
    def responder(request: httpx.Request) -> httpx.Response:
        body = request.content
        if b'"id":"404"' in body:
            return httpx.Response(
                404,
                json={"type": "x/package-not-found", "title": "nf", "status": 404},
                headers={"content-type": "application/problem+json"},
            )
        if b'"id":"429"' in body:
            return httpx.Response(
                429,
                json={"type": "x/rate-limited", "title": "rl", "status": 429},
                headers={"content-type": "application/problem+json", "Retry-After": "1"},
            )
        return httpx.Response(200, content=load("validation/patient_valid.json"))

    mock_router.add("POST", PATH, responder=responder)
    client = make_client(retries=0)
    ids = ["1", "404", "2", "429", "3"]
    results = client.validate_many(
        [{"resourceType": "Patient", "id": i} for i in ids], fhir_version="R4", concurrency=2
    )
    assert [type(r) for r in results] == [
        ValidationResult,
        NotFoundError,
        ValidationResult,
        RateLimitError,
        ValidationResult,
    ]


def test_concurrency_limit_is_respected(
    make_client: ClientFactory, mock_router: MockRouter
) -> None:
    _ok(mock_router)
    client = make_client()
    results = client.validate_many(
        [{"resourceType": "Patient"}] * 60, fhir_version="R4", concurrency=10
    )
    assert len(results) == 60
    assert 1 <= mock_router.max_in_flight <= 10


@pytest.mark.parametrize("bad", [0, -1])
def test_invalid_concurrency(client: Client, bad: int) -> None:
    with pytest.raises(InputError, match="concurrency"):
        client.validate_many([{"resourceType": "Patient"}], fhir_version="R4", concurrency=bad)


def test_shared_option_errors_raise_before_sending(client: Client, mock_router: MockRouter) -> None:
    with pytest.raises(InputError):
        client.validate_many([{"resourceType": "Patient"}], fhir_version="R6")
    assert mock_router.requests == []


def test_empty_input(client: Client) -> None:
    assert client.validate_many([], fhir_version="R4") == []


def test_raw_mode_in_batch(client: Client, mock_router: MockRouter) -> None:
    _ok(mock_router)
    results = client.validate_many([{"resourceType": "Patient"}] * 3, fhir_version="R4", raw=True)
    assert [r.status_code for r in results if isinstance(r, RawResponse)] == [200, 200, 200]


def test_sc005_thousand_resources_no_leaks(
    mock_router: MockRouter, client_kind: str, anyio_backend: str
) -> None:
    """SC-005: 1,000 inputs → 1,000 entries; every response stream is closed afterwards."""
    _ok(mock_router)
    opened: list[httpx.Response] = []

    def responder(request: httpx.Request) -> httpx.Response:
        response = httpx.Response(200, content=load("validation/patient_valid.json"))
        opened.append(response)
        return response

    mock_router.routes.clear()
    mock_router.add("POST", PATH, responder=responder)
    resources = [{"resourceType": "Patient", "id": str(i)} for i in range(1000)]
    if client_kind == "sync":
        with (
            httpx.Client(transport=mock_router.transport()) as http,
            Client("https://fvs.test", http_client=http) as c,
        ):
            results = c.validate_many(resources, fhir_version="R4", concurrency=16)
    else:
        import anyio

        async def run() -> list[ValidationResult | OperationOutcomeResult | RawResponse | FVSError]:
            async with (
                httpx.AsyncClient(transport=mock_router.async_transport()) as http,
                AsyncClient("https://fvs.test", http_client=http) as c,
            ):
                return await c.validate_many(resources, fhir_version="R4", concurrency=16)

        results = anyio.run(run, backend=anyio_backend)
    gc.collect()
    assert len(results) == 1000
    assert all(isinstance(r, ValidationResult) for r in results)
    assert len(opened) == 1000
    assert all(r.is_closed for r in opened)
