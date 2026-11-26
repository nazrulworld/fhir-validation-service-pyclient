"""Helpers validating SDK requests and fixture responses against the pinned OpenAPI contract."""

from __future__ import annotations

import json
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import Any

import httpx
from openapi_core import Config, OpenAPI
from openapi_core.testing import MockRequest, MockResponse

SNAPSHOT = Path(__file__).with_name("fvs-openapi-v1.0.0.yaml")
HOST = "http://localhost:8880"  # the contract's server URL


def _json(value: bytes) -> Any:
    return json.loads(value)


def _text(value: bytes) -> str:
    return value.decode()


# The contract uses FHIR and RFC 9457 media types openapi-core doesn't decode by default.
_DESERIALIZERS: dict[str, Callable[[bytes], Any]] = {
    "application/fhir+json": _json,
    "application/problem+json": _json,
    "application/fhir+xml": _text,
    "application/xml": _text,
    "text/xml": _text,
}


@cache
def openapi() -> OpenAPI:
    config = Config(extra_media_type_deserializers=_DESERIALIZERS)
    return OpenAPI.from_file_path(str(SNAPSHOT), config=config)


def to_mock_request(request: httpx.Request) -> MockRequest:
    """Convert an ``httpx.Request`` built by the SDK into an openapi-core request."""
    content = request.read()
    return MockRequest(
        HOST,
        request.method.lower(),
        request.url.path,
        args=dict(request.url.params),
        headers=dict(request.headers),
        data=content or None,
        content_type=request.headers.get("content-type", "application/json"),
    )


def check_request(request: httpx.Request) -> None:
    """Raise if ``request`` does not match the contract."""
    openapi().validate_request(to_mock_request(request))


def check_response(
    request: httpx.Request,
    status: int,
    body: bytes,
    content_type: str,
    headers: dict[str, str] | None = None,
) -> None:
    """Raise if a response with ``status``/``body`` is not allowed for ``request``."""
    response = MockResponse(
        body, status_code=status, headers=headers or {}, content_type=content_type
    )
    openapi().validate_response(to_mock_request(request), response)
