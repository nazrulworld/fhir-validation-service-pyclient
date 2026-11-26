"""Logging: NullHandler, per-attempt DEBUG records, nothing secret logged (T018)."""

from __future__ import annotations

import logging

import httpx
import pytest

from fvs_client import Client
from fvs_client._logging import logger, redact_headers
from fvs_client._requests import RequestSpec
from tests.conftest import MockRouter

SECRET = "s3cr3t-key-value"


def test_logger_has_null_handler() -> None:
    assert logger.name == "fvs_client"
    assert any(isinstance(h, logging.NullHandler) for h in logger.handlers)


def test_redact_headers() -> None:
    out = redact_headers({"Authorization": f"Bearer {SECRET}", "Accept": "application/json"})
    assert out == {"Authorization": "**********", "Accept": "application/json"}


def test_attempt_record_has_fields_and_no_secrets(
    mock_router: MockRouter, caplog: pytest.LogCaptureFixture
) -> None:
    mock_router.add("POST", "/R4/thing", json={"ok": True}, headers={"X-Request-Id": "rid-9"})
    http = httpx.Client(transport=mock_router.transport())
    body = b'{"resourceType":"Patient","name":[{"family":"Secretsson"}]}'
    spec = RequestSpec(
        method="POST",
        path="/R4/thing",
        params={"tx": "https://tx.secret.example/fhir"},
        accept="application/json",
        content=body,
        content_type="application/fhir+json",
    )
    with (
        caplog.at_level(logging.DEBUG, logger="fvs_client"),
        Client("https://fvs.test", api_key=SECRET, http_client=http) as c,
    ):
        c._request(spec, lambda raw: raw)  # pyright: ignore[reportPrivateUsage]
    http.close()

    records = [r for r in caplog.records if r.name == "fvs_client"]
    assert records, "expected at least one log record"
    attempt = records[-1]
    assert attempt.levelno == logging.DEBUG
    msg = attempt.getMessage()
    for expected in ("POST", "/R4/thing", "200", "rid-9", "attempt 1"):
        assert expected in msg
    assert " ms" in msg
    text = caplog.text
    assert SECRET not in text
    assert "Authorization" not in text
    assert "Secretsson" not in text
    assert "tx.secret.example" not in text
