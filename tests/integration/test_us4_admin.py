"""US4 lifecycle against a live FHIR Validation Service 1.0 (quickstart §6) (T073).

Needs FVS_IT_ADMIN_API_KEY and outbound access to the FHIR package registry.

Registration downloads the IG from the public FHIR package registries, which are sometimes
unavailable. A registry failure is retried and then, only if the registries really are unhealthy,
reported as a skip; set ``FVS_IT_STRICT_REGISTRY=1`` to fail instead.
"""

from __future__ import annotations

import os
import time

import httpx
import pytest

from fvs_client import (
    AccessChange,
    APIError,
    BadRequestError,
    Client,
    FVSTimeoutError,
    IgPackageResult,
    IgRef,
    PermissionDeniedError,
    ProblemType,
)

pytestmark = pytest.mark.integration

IG = IgRef("hl7.fhir.uv.ips", "1.1.0")
PATIENT = {"resourceType": "Patient", "active": True}

# Package metadata URLs of the service's default sources (FV_PACKAGE_SOURCES in FVS 1.0.0).
REGISTRIES = ("https://packages.fhir.org", "https://packages2.fhir.org/packages")
REGISTRY_PROBLEMS = {ProblemType.PACKAGE_NOT_FOUND, ProblemType.DEPENDENCY_NOT_FOUND}
ATTEMPTS = 3
PAUSE_SECONDS = 15.0


def _registry_failure(exc: Exception) -> bool:
    """Whether ``exc`` is how the service reports a registry it could not use."""
    if isinstance(exc, FVSTimeoutError):
        return True
    return isinstance(exc, APIError) and exc.problem_type in REGISTRY_PROBLEMS


def _unhealthy_registries(name: str, version: str) -> list[str]:
    """Registries that cannot serve ``name#version`` right now (each with the reason)."""
    unhealthy = []
    for base in REGISTRIES:
        try:
            response = httpx.get(f"{base}/{name}", timeout=15.0, follow_redirects=True)
            if response.status_code != 200:
                unhealthy.append(f"{base}: HTTP {response.status_code}")
            elif version not in response.json().get("versions", {}):
                unhealthy.append(f"{base}: {version} not listed")
        except (httpx.HTTPError, ValueError) as exc:
            unhealthy.append(f"{base}: {type(exc).__name__}: {exc}")
    return unhealthy


def _register(admin: Client, ig: IgRef) -> IgPackageResult:
    """Register ``ig``, retrying registry failures; skip only during a real registry outage."""
    assert ig.version is not None
    for attempt in range(1, ATTEMPTS + 1):
        try:
            return admin.packages.register(ig.name, ig.version)
        except (APIError, FVSTimeoutError) as exc:
            if not _registry_failure(exc):
                raise
            if attempt < ATTEMPTS:
                time.sleep(PAUSE_SECONDS)
                continue
            unhealthy = _unhealthy_registries(ig.name, ig.version)
            if not unhealthy or os.environ.get("FVS_IT_STRICT_REGISTRY") == "1":
                raise  # the registries are fine (or strict mode): this is a real failure
            pytest.skip(
                f"FHIR package registry outage after {ATTEMPTS} attempts ({exc}); "
                + "; ".join(unhealthy)
            )
    raise AssertionError("unreachable")


def test_admin_lifecycle(it_admin_client: Client, it_client: Client) -> None:
    reg = _register(it_admin_client, IG)
    assert reg.version == "1.1.0"
    assert reg.name is not None

    deps = it_admin_client.packages.dependencies(reg.name, reg.version)
    assert any(d.startswith("hl7.fhir.r4.core#") for d in deps.dependencies)

    inc = it_admin_client.contexts.include("R4", IgRef(reg.name, reg.version))
    assert inc.key == "hl7.fhir.uv.ips#1.1.0"
    try:
        result = it_client.validate(PATIENT, fhir_version="R4", ig=inc.key)
        assert result.context.key == inc.key

        it_admin_client.contexts.update("R4", inc.key, AccessChange(shareable=True))
    finally:
        it_admin_client.contexts.exclude("R4", inc.key)

    with pytest.raises(BadRequestError) as info:
        it_client.validate(PATIENT, fhir_version="R4", ig=inc.key)
    assert info.value.problem_type == ProblemType.INVALID_REQUEST


def test_validate_key_cannot_administer(it_client: Client) -> None:
    with pytest.raises(PermissionDeniedError):
        it_client.contexts.include("R4", IG)
