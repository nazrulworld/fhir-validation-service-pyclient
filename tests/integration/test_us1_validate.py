"""US1 against a live FHIR Validation Service 1.0 (quickstart §4) (T037)."""

from __future__ import annotations

import pytest

from fvs_client import Client, RawResponse, ResultFormat, Severity

pytestmark = pytest.mark.integration

VALID = {"resourceType": "Patient", "active": True}
INVALID = {
    "resourceType": "Patient",
    "active": True,
    "gender": "unknown-value",
    "birthDate": "2020-13-45",
}


def test_valid_patient_has_only_the_narrative_warning(it_client: Client) -> None:
    result = it_client.validate(VALID, fhir_version="R4")
    assert result.valid is True
    assert result.context.key == "base"
    assert result.meta.request_id
    assert any(i.severity is Severity.WARNING and "dom-6" in i.message for i in result.issues)


def test_invalid_patient_reports_errors(it_client: Client) -> None:
    result = it_client.validate(INVALID, fhir_version="r4")
    assert result.valid is False
    assert len(result.errors) >= 2


def test_operation_outcome_json(it_client: Client) -> None:
    oo = it_client.validate(
        INVALID, fhir_version="R4", result_format=ResultFormat.OPERATION_OUTCOME_JSON
    )
    assert isinstance(oo.body, dict)
    assert oo.body["resourceType"] == "OperationOutcome"
    assert oo.has_errors


def test_raw_mode(it_client: Client) -> None:
    raw = it_client.validate(VALID, fhir_version="R4", raw=True)
    assert isinstance(raw, RawResponse)
    assert raw.status_code == 200
    assert raw.json()["valid"] is True


def test_xml_resource(it_client: Client) -> None:
    xml = '<Patient xmlns="http://hl7.org/fhir"><active value="true"/></Patient>'
    assert it_client.validate(xml, fhir_version="R4").valid is True


def test_comma_separated_profiles_are_split_by_the_server(it_client: Client) -> None:
    """Research R13: profiles are sent comma-joined (as %2C); the server must split them.

    Two distinct core URLs are used: FVS 1.0.0 does not resolve ``url|version`` for
    core-spec profiles (``Patient|4.0.1`` is ``unknown-profile`` even on its own).
    """
    patient = "http://hl7.org/fhir/StructureDefinition/Patient"
    resource = "http://hl7.org/fhir/StructureDefinition/Resource"
    result = it_client.validate(VALID, fhir_version="R4", profiles=[patient, resource])
    assert {patient, resource} <= set(result.applied_profiles)
