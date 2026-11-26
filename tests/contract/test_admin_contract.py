"""SDK-built admin/package requests and fixture responses match the pinned contract (T071)."""

from __future__ import annotations

import io
from collections.abc import Callable, Iterator
from typing import Any

import httpx
import pytest

from fvs_client import AccessChange, Client, IgRef, TerminologySettings
from tests.conftest import MockRouter
from tests.contract._openapi import check_request, check_response
from tests.fixtures import load

HOST = "http://localhost:8880"


@pytest.fixture
def admin(mock_router: MockRouter) -> Iterator[tuple[Client, MockRouter]]:
    http = httpx.Client(transport=mock_router.transport())
    with Client(HOST, api_key="admin-key", http_client=http) as c:
        yield c, mock_router
    http.close()


# (operation id, method, path, fixture, call)
CASES: list[tuple[str, str, str, str, Callable[[Client], Any]]] = [
    (
        "validatorApiIncludeIg (single)",
        "POST",
        "/R4/validator",
        "admin/include_single.json",
        lambda c: c.contexts.include(
            "R4",
            IgRef("hl7.fhir.uv.ips", "1.1.x"),
            shareable=True,
            terminology=TerminologySettings(mode="server", server="https://tx.fhir.org/r4"),
        ),
    ),
    (
        "validatorApiIncludeIg (two)",
        "POST",
        "/R4/validator",
        "admin/include_two.json",
        lambda c: c.contexts.include(
            "R4", (IgRef("a.ig", "1.0.0"), IgRef("b.ig")), shareable=False
        ),
    ),
    (
        "validatorApiExcludeIg",
        "DELETE",
        "/R4/validator",
        "admin/exclude.json",
        lambda c: c.contexts.exclude("R4", "hl7.fhir.uv.ips#1.1.0"),
    ),
    (
        "validatorApiChangeIncludedIg",
        "PATCH",
        "/R4/validator",
        "admin/context_access.json",
        lambda c: c.contexts.update(
            "R4", "hl7.fhir.uv.ips#1.1.0", AccessChange(shareable=True, owner="acme")
        ),
    ),
    (
        "igPackageApiUploadIg",
        "POST",
        "/igs/upload",
        "admin/ig_registration.json",
        lambda c: c.packages.upload(io.BytesIO(b"\x1f\x8b archive"), shareable=False),
    ),
    (
        "igPackageApiRegisterIg (name)",
        "POST",
        "/igs/register",
        "admin/ig_registration.json",
        lambda c: c.packages.register("hl7.fhir.uv.ips", "1.1.x"),
    ),
    (
        "igPackageApiRegisterIg (url)",
        "POST",
        "/igs/register",
        "admin/ig_registration.json",
        lambda c: c.packages.register(download_url="https://example.org/ips.tgz"),
    ),
    (
        "igPackageApiChangeAccess",
        "PATCH",
        "/igs/hl7.fhir.uv.ips/1.1.0",
        "admin/ig_access.json",
        lambda c: c.packages.update("hl7.fhir.uv.ips", "1.1.0", AccessChange(shareable=False)),
    ),
    (
        "igPackageApiGetDependenciesGraph",
        "GET",
        "/igs/hl7.fhir.uv.ips/1.1.0/dependencies",
        "admin/dependencies.json",
        lambda c: c.packages.dependencies("hl7.fhir.uv.ips", "1.1.0"),
    ),
    (
        "igPackageApiGenerateConformanceReport",
        "GET",
        "/igs/hl7.fhir.uv.ips/1.1.0/conformance",
        "admin/files.json",
        lambda c: c.packages.files("hl7.fhir.uv.ips", "1.1.0"),
    ),
]


@pytest.mark.filterwarnings("ignore::DeprecationWarning")
@pytest.mark.parametrize(
    ("op", "method", "path", "fixture", "call"), CASES, ids=[c[0] for c in CASES]
)
def test_admin_request_and_response_match_contract(  # noqa: PLR0917 - parametrised
    admin: tuple[Client, MockRouter],
    op: str,
    method: str,
    path: str,
    fixture: str,
    call: Callable[[Client], Any],
) -> None:
    client, router = admin
    router.add(method, path, content=load(fixture), content_type="application/json")
    call(client)
    request = router.last
    check_request(request)
    check_response(request, 200, load(fixture), "application/json")


@pytest.mark.parametrize(
    ("status", "problem"),
    [
        (403, "forbidden"),
        (404, "package-not-found"),
        (409, "alias-conflict"),
        (424, "dependency-not-found"),
    ],
)
def test_include_error_fixtures_match_contract(status: int, problem: str) -> None:
    request = httpx.Request(
        "POST",
        f"{HOST}/R4/validator",
        headers={"Authorization": "Bearer k", "Content-Type": "application/json"},
        content=b'{"igPackageId":"a"}',
    )
    check_response(request, status, load(f"problems/{problem}.json"), "application/problem+json")
