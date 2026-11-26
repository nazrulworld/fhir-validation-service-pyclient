"""Resource input handling: content-type sniffing and file streaming (T031)."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from fvs_client import InputError
from fvs_client._inputs import prepare_resource
from fvs_client._requests import FileBody

FHIR_JSON = "application/fhir+json"
FHIR_XML = "application/fhir+xml"


def test_dict_is_json_encoded() -> None:
    body, ctype = prepare_resource({"resourceType": "Patient", "name": [{"family": "Ærø"}]}, None)
    assert ctype == FHIR_JSON
    assert isinstance(body, bytes)
    assert body == '{"resourceType":"Patient","name":[{"family":"Ærø"}]}'.encode()


@pytest.mark.parametrize(
    ("resource", "ctype"),
    [
        ('{"resourceType":"Patient"}', FHIR_JSON),
        (b'  \n{"resourceType":"Patient"}', FHIR_JSON),
        ('<Patient xmlns="http://hl7.org/fhir"/>', FHIR_XML),
        (b"\xef\xbb\xbf<?xml version='1.0'?><Patient/>", FHIR_XML),
        ("\t\r\n <Patient/>", FHIR_XML),
    ],
)
def test_text_and_bytes_are_sniffed(resource: str | bytes, ctype: str) -> None:
    body, got = prepare_resource(resource, None)
    assert got == ctype
    assert body == (resource.encode() if isinstance(resource, str) else resource)


@pytest.mark.parametrize("resource", ["not fhir", b"", "   ", b"[1,2]", "Patient"])
def test_unrecognised_text_is_input_error(resource: str | bytes) -> None:
    with pytest.raises(InputError, match=r"JSON|XML"):
        prepare_resource(resource, None)


@pytest.mark.parametrize("resource", [123, None, ["a"], 1.5])
def test_unsupported_types_are_input_error(resource: object) -> None:
    with pytest.raises(InputError):
        prepare_resource(resource, None)  # type: ignore[arg-type]


def test_explicit_content_type_overrides_sniffing() -> None:
    body, ctype = prepare_resource("not fhir", "text/xml")
    assert (body, ctype) == (b"not fhir", "text/xml")
    _, ctype = prepare_resource({"resourceType": "Patient"}, "application/json")
    assert ctype == "application/json"


@pytest.mark.parametrize(
    ("name", "content", "ctype"),
    [
        ("p.json", b'{"resourceType":"Patient"}', FHIR_JSON),
        ("p.xml", b"<Patient/>", FHIR_XML),
        ("p.JSON", b"<Patient/>", FHIR_JSON),
        ("p.fhir", b"<Patient/>", FHIR_XML),
        ("p.txt", b' {"a":1}', FHIR_JSON),
    ],
)
def test_path_is_streamed(tmp_path: Path, name: str, content: bytes, ctype: str) -> None:
    path = tmp_path / name
    path.write_bytes(content)
    body, got = prepare_resource(path, None)
    assert got == ctype
    assert isinstance(body, FileBody)
    assert body.path == path
    assert b"".join(body.iter_sync()) == content


def test_path_streams_in_chunks(tmp_path: Path) -> None:
    path = tmp_path / "big.json"
    path.write_bytes(b"{" + b" " * 200_000 + b"}")
    body, _ = prepare_resource(path, None)
    assert isinstance(body, FileBody)
    chunks = list(body.iter_sync())
    assert len(chunks) > 1
    assert sum(map(len, chunks)) == 200_002


def test_unsniffable_path_is_input_error(tmp_path: Path) -> None:
    path = tmp_path / "x.bin"
    path.write_bytes(b"\x00\x01")
    with pytest.raises(InputError):
        prepare_resource(path, None)


def test_missing_path_is_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="not a readable file"):
        prepare_resource(tmp_path / "nope.json", None)


@given(ws=st.text(alphabet=" \t\r\n", max_size=20), xml=st.booleans())
def test_leading_whitespace_never_changes_sniffed_type(ws: str, xml: bool) -> None:
    doc = "<Patient/>" if xml else '{"resourceType":"Patient"}'
    _, ctype = prepare_resource(ws + doc, None)
    assert ctype == (FHIR_XML if xml else FHIR_JSON)
