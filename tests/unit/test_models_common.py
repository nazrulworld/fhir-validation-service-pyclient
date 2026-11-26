"""Shared models: enums, rate-limit info, response meta, raw response, to_dict (T016)."""

from __future__ import annotations

import dataclasses
import enum

import pytest

from fvs_client import (
    FhirVersion,
    InputError,
    RateLimitInfo,
    RawResponse,
    ResponseMeta,
    Severity,
    ValidationIssue,
)
from fvs_client._parsing import build_meta, build_raw, coerce_enum


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("stu3", FhirVersion.STU3),
        ("Stu3", FhirVersion.STU3),
        ("r4", FhirVersion.R4),
        ("R4B", FhirVersion.R4B),
        ("r4b", FhirVersion.R4B),
        ("r5", FhirVersion.R5),
        (FhirVersion.R5, FhirVersion.R5),
        (" R4 ", FhirVersion.R4),
    ],
)
def test_fhir_version_parse(value: str, expected: FhirVersion) -> None:
    assert FhirVersion.parse(value) is expected


@pytest.mark.parametrize("value", ["R6", "DSTU2", "", "4.0.1", "R 4"])
def test_fhir_version_parse_rejects_unsupported(value: str) -> None:
    with pytest.raises(InputError, match="FHIR version"):
        FhirVersion.parse(value)


def test_rate_limit_info_from_headers() -> None:
    meta = build_meta(
        200,
        {
            "RateLimit-Limit": "30",
            "ratelimit-remaining": "29",
            "RateLimit-Reset": "61",
            "Retry-After": "12",
            "X-Request-Id": "abc",
        },
        elapsed=0.25,
        attempts=1,
    )
    assert meta.rate_limit == RateLimitInfo(
        limit=30, remaining=29, reset_seconds=61, retry_after_seconds=12
    )
    assert meta == ResponseMeta(
        status_code=200,
        request_id="abc",
        rate_limit=meta.rate_limit,
        elapsed_seconds=0.25,
        attempts=1,
    )


def test_rate_limit_info_absent_headers_are_none() -> None:
    meta = build_meta(200, {}, elapsed=0.0, attempts=1)
    assert meta.rate_limit == RateLimitInfo()
    assert meta.request_id is None
    assert meta.rate_limit.limit is None


def test_rate_limit_garbage_header_is_none() -> None:
    meta = build_meta(200, {"RateLimit-Limit": "lots", "Retry-After": "Wed, 21 Oct 2015"}, 0.0, 1)
    assert meta.rate_limit.limit is None
    assert meta.rate_limit.retry_after_seconds is None


def test_raw_response() -> None:
    meta = build_meta(200, {"X-Request-Id": "r1"}, 0.1, 1)
    raw = build_raw(
        200, {"Content-Type": "application/json", "X-Request-Id": "r1"}, b'{"a": 1}', meta
    )
    assert isinstance(raw, RawResponse)
    assert raw.status_code == 200
    assert raw.headers["content-type"] == "application/json"
    assert raw.headers["CONTENT-TYPE"] == "application/json"
    assert "x-request-id" in raw.headers
    assert raw.content == b'{"a": 1}'
    assert raw.text == '{"a": 1}'
    assert raw.json() == {"a": 1}
    assert raw.meta is meta


def test_raw_response_headers_are_read_only() -> None:
    raw = build_raw(200, {"A": "1"}, b"", build_meta(200, {}, 0.0, 1))
    with pytest.raises(TypeError):
        raw.headers["A"] = "2"  # type: ignore[index]
    with pytest.raises(dataclasses.FrozenInstanceError):
        raw.status_code = 500  # type: ignore[misc]


def test_to_dict_converts_enums_and_nests() -> None:
    issue = ValidationIssue(severity=Severity.ERROR, location="Patient.x", message="bad")
    d = issue.to_dict()
    assert d == {"severity": "ERROR", "location": "Patient.x", "message": "bad"}
    assert type(d["severity"]) is str


def test_to_dict_on_raw_response() -> None:
    raw = build_raw(200, {"A": "1"}, b"x", build_meta(200, {"A": "1"}, 0.0, 1))
    d = raw.to_dict()
    assert d["headers"] == {"a": "1"}
    assert d["meta"]["rate_limit"]["limit"] is None


class _Colour(enum.StrEnum):
    RED = "red"


def test_unknown_enum_value_is_kept_as_str() -> None:
    assert coerce_enum(_Colour, "red") is _Colour.RED
    value = coerce_enum(_Colour, "ultraviolet")
    assert value == "ultraviolet"
    assert not isinstance(value, _Colour)
    assert coerce_enum(_Colour, None) is None


def test_severity_is_error() -> None:
    assert Severity.FATAL.is_error
    assert Severity.ERROR.is_error
    assert not Severity.WARNING.is_error
    assert not Severity.INFORMATION.is_error
