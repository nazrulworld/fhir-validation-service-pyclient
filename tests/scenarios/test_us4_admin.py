"""US4 acceptance scenarios 1-6: manage IG packages and validator contexts (T072)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from fvs_client import (
    AccessChange,
    Client,
    FVSConnectionError,
    IgRef,
    PermissionDeniedError,
    RawResponse,
    ServiceUnavailableError,
)
from tests.conftest import ClientFactory, MockRouter
from tests.fixtures import load


def _ok(router: MockRouter, method: str, path: str, fixture: str) -> None:
    router.add(method, path, content=load(fixture), content_type="application/json")


def test_1_upload_archive(client: Client, mock_router: MockRouter, tmp_path: Path) -> None:
    _ok(mock_router, "POST", "/igs/upload", "admin/ig_registration.json")
    archive = tmp_path / "ips.tgz"
    archive.write_bytes(b"\x1f\x8b" + b"p" * 300_000)
    result = client.packages.upload(archive, shareable=False)
    assert (result.name, result.version, result.owner, result.shareable) == (
        "hl7.fhir.uv.ips",
        "1.1.0",
        "acme",
        True,
    )
    req = mock_router.last
    assert req.headers["content-type"].startswith("multipart/form-data")
    body = req.content
    assert b'name="file"; filename="ips.tgz"' in body
    assert b"p" * 300_000 in body
    assert b'name="shareable"\r\n\r\nfalse' in body


@pytest.mark.parametrize("version", ["1.1.0", "latest", "1.1.x"])
def test_2_register(client: Client, mock_router: MockRouter, version: str) -> None:
    _ok(mock_router, "POST", "/igs/register", "admin/ig_registration.json")
    result = client.packages.register("hl7.fhir.uv.ips", version)
    assert (result.version, result.requested_version, result.downloaded) == (
        "1.1.0",
        "latest",
        True,
    )
    assert json.loads(mock_router.last.content)["version"] == version


def test_3_include_single_and_two(client: Client, mock_router: MockRouter) -> None:
    _ok(mock_router, "POST", "/R4/validator", "admin/include_single.json")
    single = client.contexts.include("R4", "hl7.fhir.uv.ips#1.1.x")
    assert single.key == "hl7.fhir.uv.ips#1.1.0"
    assert single.resolved
    mock_router.routes.clear()
    _ok(mock_router, "POST", "/R4/validator", "admin/include_two.json")
    two = client.contexts.include("R4", (IgRef("a.ig", "1.0.0"), IgRef("b.ig")), shareable=False)
    assert two.aliases == ("b.ig#2.0.0|a.ig#1.0.0", "a.ig#1.0.0")
    assert two.warnings
    assert json.loads(mock_router.last.content)["igPackages"][1] == {"igPackageId": "b.ig"}


def test_4_update_and_exclude(client: Client, mock_router: MockRouter) -> None:
    mock_router.add(
        "PATCH",
        "/R4/validator",
        json={
            "status": "success",
            "fhirVersion": "R4",
            "igPackage": "hl7.fhir.uv.ips#1.1.0",
            "owner": "acme",
            "shareable": True,
            "warnings": ["shareable: false ignored: access control is disabled"],
        },
    )
    upd = client.contexts.update("R4", "hl7.fhir.uv.ips#1.1.0", AccessChange(shareable=False))
    assert upd.warnings == ("shareable: false ignored: access control is disabled",)
    _ok(mock_router, "DELETE", "/R4/validator", "admin/exclude.json")
    exc = client.contexts.exclude("R4", "hl7.fhir.uv.ips#1.1.0")
    assert exc.excluded == "hl7.fhir.uv.ips#1.1.0"
    assert mock_router.last.url.params["ig"] == "hl7.fhir.uv.ips#1.1.0"


def test_5_validate_key_gets_permission_denied(client: Client, mock_router: MockRouter) -> None:
    mock_router.add(
        "POST",
        "/igs/register",
        403,
        content=load("problems/forbidden.json"),
        content_type="application/problem+json",
    )
    with pytest.raises(PermissionDeniedError):
        client.packages.register("hl7.fhir.uv.ips")


def test_6_dependencies(client: Client, mock_router: MockRouter) -> None:
    _ok(mock_router, "GET", "/igs/hl7.fhir.uv.ips/1.1.0/dependencies", "admin/dependencies.json")
    deps = client.packages.dependencies("hl7.fhir.uv.ips", "1.1.0")
    assert deps.dependencies == ("hl7.fhir.r4.core#4.0.1", "hl7.terminology.r4#5.0.0")


def test_admin_ops_not_retried_by_default(
    client: Client, mock_router: MockRouter, sleeps: list[float]
) -> None:
    for _ in range(2):  # one for the default call, one for the retried call
        mock_router.add(
            "POST",
            "/igs/register",
            503,
            content=load("problems/overloaded.json"),
            content_type="application/problem+json",
            headers={"Retry-After": "1"},
        )
    _ok(mock_router, "POST", "/igs/register", "admin/ig_registration.json")
    with pytest.raises(ServiceUnavailableError):
        client.packages.register("hl7.fhir.uv.ips")
    assert sleeps == []
    assert client.packages.register("hl7.fhir.uv.ips", retries=1).version == "1.1.0"  # 503 retried
    assert sleeps == [1.0]


def test_admin_connect_error_never_retried(
    make_client: ClientFactory, mock_router: MockRouter, sleeps: list[float]
) -> None:
    mock_router.add("POST", "/igs/register", exc=httpx.ConnectError("refused"))
    with pytest.raises(FVSConnectionError):
        make_client().packages.register("hl7.fhir.uv.ips", retries=3)
    assert sleeps == []


def test_files_is_deprecated(client: Client, mock_router: MockRouter) -> None:
    _ok(mock_router, "GET", "/igs/hl7.fhir.uv.ips/1.1.0/conformance", "admin/files.json")
    with pytest.warns(DeprecationWarning, match="deprecated"):
        files = client.packages.files("hl7.fhir.uv.ips", "1.1.0")
    assert files.files


def test_raw_mode_on_admin_ops(client: Client, mock_router: MockRouter) -> None:
    _ok(mock_router, "POST", "/R4/validator", "admin/include_single.json")
    raw = client.contexts.include("R4", "hl7.fhir.uv.ips", raw=True)
    assert isinstance(raw, RawResponse)
    assert raw.json()["key"]["igPackage"] == "hl7.fhir.uv.ips#1.1.0"
