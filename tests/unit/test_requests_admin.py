"""Request building for administrative and package operations (T069)."""

from __future__ import annotations

import io
import json

import httpx
import pytest

from fvs_client import AccessChange, IgRef, InputError, TerminologySettings
from fvs_client._requests import (
    RequestSpec,
    build_context_update,
    build_dependencies,
    build_exclude,
    build_files,
    build_include,
    build_package_update,
    build_register,
    build_upload,
)


def _url(spec: RequestSpec) -> httpx.URL:
    return httpx.Request(spec.method, "https://fvs.test" + spec.path, params=dict(spec.params)).url


def test_include_single() -> None:
    spec = build_include("r4", IgRef("hl7.fhir.uv.ips", "1.1.x"), shareable=None, terminology=None)
    assert (spec.method, spec.path, spec.is_admin) == ("POST", "/R4/validator", True)
    assert spec.json == {"igPackageId": "hl7.fhir.uv.ips", "igPackageVersion": "1.1.x"}


def test_include_single_without_version_and_with_options() -> None:
    spec = build_include(
        "R4",
        "hl7.fhir.uv.ips",
        shareable=False,
        terminology=TerminologySettings(mode="server", server="https://tx.fhir.org/r4"),
    )
    assert spec.json == {
        "igPackageId": "hl7.fhir.uv.ips",
        "shareable": False,
        "terminology": {"mode": "server", "server": "https://tx.fhir.org/r4"},
    }


def test_include_two() -> None:
    spec = build_include("R4", (IgRef("a", "1.0.0"), IgRef("b")), shareable=True, terminology=None)
    assert spec.json == {
        "igPackages": [{"igPackageId": "a", "igPackageVersion": "1.0.0"}, {"igPackageId": "b"}],
        "shareable": True,
    }


def test_exclude_and_update_encode_ig() -> None:
    spec = build_exclude("R4", "a#1.0.0|b#2.0.0")
    assert (spec.method, spec.path, spec.is_admin) == ("DELETE", "/R4/validator", True)
    assert _url(spec).query == b"ig=a%231.0.0%7Cb%232.0.0"
    spec = build_context_update("R4", "a.ig#1.0.0", AccessChange(shareable=True))
    assert (spec.method, spec.is_admin) == ("PATCH", True)
    assert _url(spec).query == b"ig=a.ig%231.0.0"
    assert spec.json == {"shareable": True}


def test_upload_is_multipart_and_streamed() -> None:
    handle = io.BytesIO(b"\x1f\x8b" + b"z" * 100_000)
    spec = build_upload("pkg.tgz", handle, shareable=False)
    assert (spec.method, spec.path, spec.is_admin) == ("POST", "/igs/upload", True)
    assert spec.files[0].field == "file"
    assert spec.files[0].filename == "pkg.tgz"
    assert spec.files[0].handle is handle  # streamed from the handle, never read into the spec
    assert spec.files[0].content_type == "application/gzip"
    assert dict(spec.data) == {"shareable": "false"}
    request = httpx.Request(
        "POST",
        "https://fvs.test/igs/upload",
        files=[("file", ("pkg.tgz", handle, "application/gzip"))],
        data=dict(spec.data),
    )
    assert request.headers["content-type"].startswith("multipart/form-data; boundary=")
    assert isinstance(request.stream, httpx.SyncByteStream)


def test_register_by_name_and_by_url() -> None:
    spec = build_register(
        "hl7.fhir.uv.ips", "1.1.x", None, include_dependencies=True, shareable=True
    )
    assert (spec.method, spec.path, spec.is_admin) == ("POST", "/igs/register", True)
    assert spec.json == {
        "name": "hl7.fhir.uv.ips",
        "version": "1.1.x",
        "includeDependency": True,
        "shareable": True,
    }
    spec = build_register(
        None, "latest", "https://example.org/a.tgz", include_dependencies=False, shareable=False
    )
    assert spec.json == {
        "downloadUrl": "https://example.org/a.tgz",
        "includeDependency": False,
        "shareable": False,
    }


def test_package_paths_are_segment_encoded() -> None:
    spec = build_package_update("my/ig", "1.0.0#x", AccessChange(owner="acme"))
    assert (spec.method, spec.path, spec.is_admin) == ("PATCH", "/igs/my%2Fig/1.0.0%23x", True)
    assert spec.json == {"owner": "acme"}
    spec = build_dependencies("hl7.fhir.uv.ips", "1.1.0")
    assert (spec.method, spec.path, spec.is_admin) == (
        "GET",
        "/igs/hl7.fhir.uv.ips/1.1.0/dependencies",
        False,
    )
    spec = build_files("hl7.fhir.uv.ips", "1.1.0")
    assert (spec.method, spec.path, spec.is_admin) == (
        "GET",
        "/igs/hl7.fhir.uv.ips/1.1.0/conformance",
        False,
    )


def test_package_update_rejects_terminology() -> None:
    with pytest.raises(InputError, match="terminology"):
        build_package_update(
            "a", "1.0.0", AccessChange(terminology=TerminologySettings(mode="none"))
        )


def test_json_bodies_serialise() -> None:
    spec = build_include(
        "R4", "a#1.0.0", shareable=None, terminology=TerminologySettings(mode="none")
    )
    assert json.loads(json.dumps(spec.json)) == spec.json
