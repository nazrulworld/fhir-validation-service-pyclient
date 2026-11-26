"""SC-009: the API key never appears in reprs, errors, raw responses or logs (T089)."""

from __future__ import annotations

import io
import logging
import warnings
from collections.abc import Callable
from typing import Any

import pytest

from fvs_client import AccessChange, Client, FVSError, InputError
from tests.conftest import ClientFactory, MockRouter
from tests.fixtures import load

SECRET = "s3cr3t-key-value"

OPERATIONS: list[tuple[str, str, Callable[[Client], Any]]] = [
    ("POST", "/R4/validate", lambda c: c.validate({"resourceType": "Patient"}, fhir_version="R4")),
    ("POST", "/R4/validator", lambda c: c.contexts.include("R4", "a.ig#1.0.0")),
    ("DELETE", "/R4/validator", lambda c: c.contexts.exclude("R4", "a.ig#1.0.0")),
    (
        "PATCH",
        "/R4/validator",
        lambda c: c.contexts.update("R4", "a.ig#1.0.0", AccessChange(shareable=True)),
    ),
    ("POST", "/igs/upload", lambda c: c.packages.upload(io.BytesIO(b"\x1f\x8b"))),
    ("POST", "/igs/register", lambda c: c.packages.register("a.ig")),
    (
        "PATCH",
        "/igs/a.ig/1.0.0",
        lambda c: c.packages.update("a.ig", "1.0.0", AccessChange(owner="acme")),
    ),
    ("GET", "/igs/a.ig/1.0.0/dependencies", lambda c: c.packages.dependencies("a.ig", "1.0.0")),
    ("GET", "/igs/a.ig/1.0.0/conformance", lambda c: c.packages.files("a.ig", "1.0.0")),
    ("GET", "/health", lambda c: c.health.check()),
    ("GET", "/health/liveness", lambda c: c.health.liveness()),
    ("GET", "/health/readiness", lambda c: c.health.readiness()),
]

ANSWERS = [
    (200, b'{"status":"UP","valid":true}', "application/json"),
    (401, load("problems/unauthorized.json"), "application/problem+json"),
    (429, load("problems/rate-limited.json"), "application/problem+json"),
    (500, load("problems/internal-error.json"), "application/problem+json"),
]


@pytest.mark.parametrize(("status", "body", "ctype"), ANSWERS, ids=lambda a: str(a)[:20])
@pytest.mark.parametrize(
    ("method", "path", "call"), OPERATIONS, ids=[f"{m} {p}" for m, p, _ in OPERATIONS]
)
def test_key_never_leaks(  # noqa: PLR0917 - parametrised
    make_client: ClientFactory,
    mock_router: MockRouter,
    caplog: pytest.LogCaptureFixture,
    method: str,
    path: str,
    call: Callable[[Client], Any],
    status: int,
    body: bytes,
    ctype: str,
) -> None:
    mock_router.add(method, path, status, content=body, content_type=ctype)
    client = make_client(api_key=SECRET, retries=0)
    seen: list[str] = [repr(client), str(client)]
    with caplog.at_level(logging.DEBUG, logger="fvs_client"), warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        try:
            result = call(client)
            seen += [repr(result), str(result.to_dict())]
        except FVSError as err:
            seen += [str(err), repr(err), repr(err.args)]
            response = getattr(err, "response", None)
            if response is not None:
                seen += [repr(response), str(response.to_dict()), response.text]
    assert mock_router.last.headers["Authorization"] == f"Bearer {SECRET}"  # it *was* sent
    seen.append(caplog.text)
    leaks = [s for s in seen if SECRET in s]
    assert leaks == []


def test_key_cannot_be_passed_through_extra_headers(
    client: Client, mock_router: MockRouter
) -> None:
    with pytest.raises(InputError) as info:
        client.validate(
            {"resourceType": "Patient"},
            fhir_version="R4",
            extra_headers={"Authorization": f"Bearer {SECRET}"},
        )
    assert SECRET not in str(info.value)
    assert mock_router.requests == []
