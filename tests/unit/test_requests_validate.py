"""Request building for POST /{version}/validate (T033)."""

from __future__ import annotations

import httpx
import pytest

from fvs_client import ResultFormat, ValidationOptions
from fvs_client._requests import build_validate


def test_path_method_and_defaults() -> None:
    spec = build_validate("r4b", {"resourceType": "Patient"}, ValidationOptions())
    assert spec.method == "POST"
    assert spec.path == "/R4B/validate"
    assert dict(spec.params) == {}
    assert spec.accept == "application/json"
    assert spec.content_type == "application/fhir+json"
    assert spec.content == b'{"resourceType":"Patient"}'
    assert spec.is_admin is False


def test_ig_is_percent_encoded_in_url() -> None:
    spec = build_validate("R4", {"resourceType": "Patient"}, ValidationOptions(ig="a.b#1.0|c#2"))
    assert dict(spec.params) == {"ig": "a.b#1.0|c#2"}
    url = httpx.Request("POST", "https://fvs.test/R4/validate", params=dict(spec.params)).url
    assert url.query == b"ig=a.b%231.0%7Cc%232"


def test_profiles_are_comma_joined() -> None:
    opts = ValidationOptions(profiles=["http://a/P|1.0", "http://b/Q"])
    spec = build_validate("R4", {"resourceType": "Patient"}, opts)
    assert spec.params["profile"] == "http://a/P|1.0,http://b/Q"


def test_tx_and_tx_mode_only_when_set() -> None:
    spec = build_validate("R4", {}, ValidationOptions(tx="https://tx.fhir.org/r4"))
    assert dict(spec.params) == {"tx": "https://tx.fhir.org/r4"}
    spec = build_validate("R4", {}, ValidationOptions(tx_mode="ecosystem"))
    assert dict(spec.params) == {"txMode": "ecosystem"}


@pytest.mark.parametrize(
    ("fmt", "accept"),
    [
        (ResultFormat.SUMMARY, "application/json"),
        (ResultFormat.OPERATION_OUTCOME_JSON, "application/fhir+json"),
        (ResultFormat.OPERATION_OUTCOME_XML, "application/fhir+xml"),
    ],
)
def test_accept_follows_result_format(fmt: ResultFormat, accept: str) -> None:
    spec = build_validate("R4", {}, ValidationOptions(result_format=fmt))
    assert spec.accept == accept


def test_xml_resource_and_content_type_override() -> None:
    spec = build_validate("R4", "<Patient/>", ValidationOptions())
    assert spec.content_type == "application/fhir+xml"
    spec = build_validate("R4", "<Patient/>", ValidationOptions(content_type="text/xml"))
    assert spec.content_type == "text/xml"
