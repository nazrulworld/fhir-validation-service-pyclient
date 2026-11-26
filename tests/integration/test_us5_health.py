"""US5 against a live FHIR Validation Service 1.0, without an API key (T084)."""

from __future__ import annotations

import pytest

from fvs_client import Client, FhirVersion, HealthStatus

pytestmark = pytest.mark.integration


def test_health_without_api_key(it_base_url: str) -> None:
    with Client(it_base_url, api_key="") as c:
        assert c.health.liveness().status is HealthStatus.UP
        assert c.health.readiness().is_ready
        health = c.health.check()
        assert FhirVersion.R4 in health.served_fhir_versions
        assert health.acl_enabled is not None
