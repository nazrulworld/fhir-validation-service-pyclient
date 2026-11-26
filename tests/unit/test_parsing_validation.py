"""Parsing of validation responses (T034)."""

from __future__ import annotations

import json

import pytest

from fvs_client import (
    FhirVersion,
    OperationOutcomeResult,
    ResultFormat,
    ServerError,
    Severity,
    TerminologyMode,
    TxSource,
    ValidationResult,
)
from fvs_client._parsing import (
    build_context_info,
    build_meta,
    build_raw,
    parse_operation_outcome,
    parse_validation,
)
from fvs_client.models import RawResponse
from tests.fixtures import load, load_json

HEADERS = {
    "Content-Type": "application/json",
    "X-Validation-Context": "base",
    "X-Validation-Context-Owner": "system",
    "X-Validation-Context-Shareable": "true",
    "X-Tx-Mode": "none",
    "X-Tx-Source": "context",
    "X-Request-Id": "rid-1",
    "RateLimit-Remaining": "29",
}


def _raw(body: bytes, headers: dict[str, str] = HEADERS, status: int = 200) -> RawResponse:
    return build_raw(status, headers, body, build_meta(status, headers, 0.01, 1))


def test_parse_invalid_patient() -> None:
    r = parse_validation(_raw(load("validation/patient_invalid.json")))
    assert isinstance(r, ValidationResult)
    assert r.valid is False
    assert len(r.issues) == 4
    assert r.issues[0].severity is Severity.ERROR
    assert r.issues[0].location == "Patient.gender"
    assert r.fhir_version is FhirVersion.R4
    assert r.applied_profiles == ()
    assert r.ig_package is None
    assert r.ig_owner == "system"
    assert r.ig_shareable is True
    assert r.context.key == "base"
    assert r.context.is_base
    assert r.context.owner == "system"
    assert r.context.shareable is True
    assert r.context.tx_mode is TerminologyMode.NONE
    assert r.context.tx_server is None
    assert r.context.tx_source is TxSource.CONTEXT
    assert r.meta.request_id == "rid-1"
    assert r.meta.rate_limit.remaining == 29
    assert r.raw == load_json("validation/patient_invalid.json")


def test_helpers() -> None:
    r = parse_validation(_raw(load("validation/patient_invalid.json")))
    assert [i.location for i in r.errors] == [
        "Patient.gender",
        "Patient.gender",
        "Patient.birthDate",
    ]
    assert [i.severity for i in r.warnings] == [Severity.WARNING]
    assert r.information == ()
    assert r.has_errors is True
    assert r.issues_by_severity(Severity.WARNING, Severity.INFORMATION) == r.warnings
    valid = parse_validation(_raw(load("validation/patient_valid.json")))
    assert valid.valid is True
    assert valid.has_errors is False
    assert valid.errors == ()


def test_fatal_counts_as_error() -> None:
    body = json.dumps(
        {"valid": False, "messages": [{"severity": "FATAL", "location": "x", "message": "m"}]}
    ).encode()
    r = parse_validation(_raw(body))
    assert r.has_errors
    assert len(r.errors) == 1


def test_unknown_fields_and_values_are_tolerated() -> None:
    data = load_json("validation/patient_valid.json")
    data["brandNewField"] = {"x": 1}
    data["fhirVersion"] = "R6"
    data["messages"].append({"severity": "HINT", "message": "new severity"})
    r = parse_validation(_raw(json.dumps(data).encode()))
    assert r.raw["brandNewField"] == {"x": 1}
    assert r.fhir_version == "R6"
    assert r.issues[-1].severity == "HINT"
    assert r.issues[-1].location is None


def test_ig_context_headers() -> None:
    headers = {
        "X-Validation-Context": "a.ig#1.0.0|b.ig#2.0.0",
        "X-Validation-Context-Owner": "acme",
        "X-Validation-Context-Shareable": "false",
        "X-Tx-Mode": "server",
        "X-Tx-Server": "https://tx.fhir.org/r4",
        "X-Tx-Source": "request",
    }
    ctx = build_context_info(headers)
    assert ctx.key == "a.ig#1.0.0|b.ig#2.0.0"
    assert not ctx.is_base
    assert ctx.shareable is False
    assert ctx.tx_mode is TerminologyMode.SERVER
    assert ctx.tx_server == "https://tx.fhir.org/r4"
    assert ctx.tx_source is TxSource.REQUEST


def test_missing_context_headers() -> None:
    ctx = build_context_info({})
    assert ctx.key == ""
    assert ctx.owner is None
    assert ctx.shareable is None
    assert ctx.tx_mode is None


def test_to_dict_round_trip() -> None:
    r = parse_validation(_raw(load("validation/patient_invalid.json")))
    d = r.to_dict()
    assert d["valid"] is False
    assert d["issues"][0]["severity"] == "ERROR"
    assert d["context"]["key"] == "base"
    json.dumps(d)  # plain data only


def test_non_object_body_is_server_error() -> None:
    with pytest.raises(ServerError):
        parse_validation(_raw(b"[]"))
    with pytest.raises(ServerError):
        parse_validation(_raw(b"<html/>"))


def test_operation_outcome_json() -> None:
    raw = _raw(
        load("validation/operation_outcome.json"),
        {**HEADERS, "Content-Type": "application/fhir+json"},
    )
    r = parse_operation_outcome(raw, ResultFormat.OPERATION_OUTCOME_JSON)
    assert isinstance(r, OperationOutcomeResult)
    assert r.format is ResultFormat.OPERATION_OUTCOME_JSON
    assert isinstance(r.body, dict)
    assert r.body["resourceType"] == "OperationOutcome"
    assert r.raw == r.body
    assert r.has_errors is True
    assert r.context.key == "base"
    assert r.meta.request_id == "rid-1"


def test_operation_outcome_json_without_errors() -> None:
    body = b'{"resourceType":"OperationOutcome","issue":[{"severity":"warning","code":"x"}]}'
    r = parse_operation_outcome(_raw(body), ResultFormat.OPERATION_OUTCOME_JSON)
    assert r.has_errors is False


def test_operation_outcome_xml() -> None:
    raw = _raw(
        load("validation/operation_outcome.xml"),
        {**HEADERS, "Content-Type": "application/fhir+xml"},
    )
    r = parse_operation_outcome(raw, ResultFormat.OPERATION_OUTCOME_XML)
    assert isinstance(r.body, str)
    assert r.body.startswith("<OperationOutcome")
    with pytest.raises(NotImplementedError, match="summary"):
        _ = r.has_errors
