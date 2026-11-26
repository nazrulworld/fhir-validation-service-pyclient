"""US1 acceptance scenarios 1-7: validate a FHIR resource (T036).

Written against the ``client`` fixture so they run on every client implementation.
"""

from __future__ import annotations

from pathlib import Path

from fvs_client import (
    Client,
    IgRef,
    OperationOutcomeResult,
    RawResponse,
    ResultFormat,
    Severity,
    TerminologyMode,
    TxSource,
    ValidationResult,
)
from tests.conftest import MockRouter
from tests.fixtures import load, load_json

BASE_HEADERS = {
    "X-Validation-Context": "base",
    "X-Validation-Context-Owner": "system",
    "X-Validation-Context-Shareable": "true",
    "X-Tx-Mode": "none",
    "X-Tx-Source": "context",
}


def _serve(router: MockRouter, fixture: str, headers: dict[str, str] | None = None) -> None:
    router.add(
        "POST",
        "/R4/validate",
        content=load(fixture),
        content_type="application/json",
        headers={**BASE_HEADERS, **(headers or {})},
    )


def test_1_valid_patient_against_core(client: Client, mock_router: MockRouter) -> None:
    _serve(mock_router, "validation/patient_valid.json")
    result = client.validate({"resourceType": "Patient", "active": True}, fhir_version="R4")
    assert isinstance(result, ValidationResult)
    assert result.valid is True
    assert not result.has_errors
    assert result.context.key == "base"
    req = mock_router.last
    assert req.url.path == "/R4/validate"
    assert "ig" not in req.url.params
    assert req.headers["Authorization"] == "Bearer test-key"


def test_2_invalid_resource_is_a_result_not_an_error(
    client: Client, mock_router: MockRouter
) -> None:
    _serve(mock_router, "validation/patient_invalid.json")
    result = client.validate(
        {"resourceType": "Patient", "gender": "unknown-value", "birthDate": "2020-13-45"},
        fhir_version="r4",
    )
    assert result.valid is False
    assert len(result.errors) == 3
    assert {i.severity for i in result.issues} == {Severity.ERROR, Severity.WARNING}
    assert all(i.message and i.location for i in result.issues)


def test_3_ig_forms_are_encoded_and_concrete_version_reported(
    client: Client, mock_router: MockRouter
) -> None:
    data = load_json("validation/patient_valid.json")
    data["igPackage"] = "hl7.fhir.uv.ips#1.1.0"
    for ig in (
        "hl7.fhir.uv.ips#1.1.0",
        "hl7.fhir.uv.ips#latest",
        "hl7.fhir.uv.ips",
        IgRef("hl7.fhir.uv.ips"),
    ):
        mock_router.add(
            "POST",
            "/R4/validate",
            json=data,
            headers={**BASE_HEADERS, "X-Validation-Context": "hl7.fhir.uv.ips#1.1.0"},
        )
        result = client.validate({"resourceType": "Patient"}, fhir_version="R4", ig=ig)
        assert result.ig_package == "hl7.fhir.uv.ips#1.1.0"
        assert result.context.key == "hl7.fhir.uv.ips#1.1.0"
        assert mock_router.last.url.params["ig"] == str(ig)
    assert b"ig=hl7.fhir.uv.ips%231.1.0" in mock_router.requests[0].url.query
    client.validate(
        {"resourceType": "Patient"},
        fhir_version="R4",
        ig=(IgRef("a", "1.0.0"), IgRef("b", "2.0.0")),
    )
    assert b"ig=a%231.0.0%7Cb%232.0.0" in mock_router.last.url.query


def test_4_operation_outcome_formats(client: Client, mock_router: MockRouter) -> None:
    mock_router.add(
        "POST",
        "/R4/validate",
        content=load("validation/operation_outcome.json"),
        content_type="application/fhir+json",
        headers=BASE_HEADERS,
    )
    oo = client.validate(
        {"resourceType": "Patient"},
        fhir_version="R4",
        result_format=ResultFormat.OPERATION_OUTCOME_JSON,
    )
    assert isinstance(oo, OperationOutcomeResult)
    assert isinstance(oo.body, dict)
    assert oo.body["resourceType"] == "OperationOutcome"
    assert mock_router.last.headers["Accept"] == "application/fhir+json"

    mock_router.routes.clear()
    mock_router.add(
        "POST",
        "/R4/validate",
        content=load("validation/operation_outcome.xml"),
        content_type="application/fhir+xml",
        headers=BASE_HEADERS,
    )
    xml = client.validate(
        {"resourceType": "Patient"},
        fhir_version="R4",
        result_format=ResultFormat.OPERATION_OUTCOME_XML,
    )
    assert isinstance(xml.body, str)
    assert "<OperationOutcome" in xml.body
    assert mock_router.last.headers["Accept"] == "application/fhir+xml"


def test_5_raw_mode_and_raw_body_on_results(client: Client, mock_router: MockRouter) -> None:
    _serve(mock_router, "validation/patient_valid.json")
    raw = client.validate({"resourceType": "Patient"}, fhir_version="R4", raw=True)
    assert isinstance(raw, RawResponse)
    assert raw.status_code == 200
    assert raw.headers["x-validation-context"] == "base"
    assert raw.json() == load_json("validation/patient_valid.json")
    parsed = client.validate({"resourceType": "Patient"}, fhir_version="R4")
    assert parsed.raw == load_json("validation/patient_valid.json")
    assert parsed.to_dict()["valid"] is True


def test_6_profiles_and_terminology_are_sent_and_reported(
    client: Client, mock_router: MockRouter
) -> None:
    _serve(
        mock_router,
        "validation/patient_valid.json",
        {"X-Tx-Mode": "server", "X-Tx-Server": "https://tx.fhir.org/r4", "X-Tx-Source": "request"},
    )
    result = client.validate(
        {"resourceType": "Patient"},
        fhir_version="R4",
        profiles=["http://hl7.org/fhir/StructureDefinition/Patient", "http://example.org/P"],
        tx="https://tx.fhir.org/r4",
        tx_mode="server",
    )
    params = mock_router.last.url.params
    assert (
        params["profile"] == "http://hl7.org/fhir/StructureDefinition/Patient,http://example.org/P"
    )
    assert params["tx"] == "https://tx.fhir.org/r4"
    assert params["txMode"] == "server"
    assert result.context.tx_mode is TerminologyMode.SERVER
    assert result.context.tx_server == "https://tx.fhir.org/r4"
    assert result.context.tx_source is TxSource.REQUEST


def test_7_xml_resource(client: Client, mock_router: MockRouter, tmp_path: Path) -> None:
    _serve(mock_router, "validation/patient_valid.json")
    xml = '<Patient xmlns="http://hl7.org/fhir"><active value="true"/></Patient>'
    result = client.validate(xml, fhir_version="R4")
    assert result.valid is True
    assert mock_router.last.headers["Content-Type"] == "application/fhir+xml"
    assert mock_router.last.content == xml.encode()

    path = tmp_path / "patient.xml"
    path.write_text(xml)
    client.validate(path, fhir_version="R4")
    assert mock_router.last.headers["Content-Type"] == "application/fhir+xml"
    assert mock_router.last.content == xml.encode()
