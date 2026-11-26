"""US4 lifecycle against a live FHIR Validation Service 1.0 (quickstart §6) (T073).

Needs FVS_IT_ADMIN_API_KEY and outbound access to the FHIR package registry.
"""

from __future__ import annotations

import pytest

from fvs_client import (
    AccessChange,
    BadRequestError,
    Client,
    IgRef,
    PermissionDeniedError,
    ProblemType,
)

pytestmark = pytest.mark.integration

IG = IgRef("hl7.fhir.uv.ips", "1.1.0")
PATIENT = {"resourceType": "Patient", "active": True}


def test_admin_lifecycle(it_admin_client: Client, it_client: Client) -> None:
    reg = it_admin_client.packages.register(IG.name, IG.version or "latest")
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
