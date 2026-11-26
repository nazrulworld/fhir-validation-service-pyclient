"""Parsing of health, liveness and readiness reports (T081)."""

from __future__ import annotations

import datetime as dt

import pytest

from fvs_client import (
    FhirVersion,
    HealthReport,
    HealthStatus,
    LivenessReport,
    ReadinessReport,
    ServiceUnavailableError,
)
from fvs_client._parsing import (
    build_meta,
    build_raw,
    finalize,
    parse_health,
    parse_liveness,
    parse_readiness,
)
from fvs_client.models import AllowlistSource, RawResponse
from tests.fixtures import load, load_json

TS = dt.datetime(2025, 10, 26, 8, 0, tzinfo=dt.UTC)  # 1761465600000 ms


def _raw(
    path: str | None, status: int = 200, content_type: str = "application/json"
) -> RawResponse:
    h = {"content-type": content_type}
    body = load(path) if path else b""
    return build_raw(status, h, body, build_meta(status, h, 0.0, 1))


def test_liveness() -> None:
    r = parse_liveness(_raw("health/liveness.json"))
    assert isinstance(r, LivenessReport)
    assert r.status is HealthStatus.UP
    assert r.timestamp == TS
    assert r.timestamp is not None
    assert r.timestamp.tzinfo is dt.UTC


def test_readiness_up() -> None:
    r = parse_readiness(_raw("health/readiness_up.json"))
    assert isinstance(r, ReadinessReport)
    assert r.is_ready
    assert (r.status, r.timestamp, r.catalog_revision, r.reasons) == (HealthStatus.UP, TS, 45, ())
    assert r.versions["R4"]["base"]["state"] == "ACTIVE"
    assert r.raw == load_json("health/readiness_up.json")


def test_readiness_down() -> None:
    r = parse_readiness(_raw("health/readiness_down.json", 503))
    assert not r.is_ready
    assert r.status is HealthStatus.DOWN
    assert r.reasons == ("R4: context hl7.fhir.uv.ips#1.1.0 is BUILDING", "draining")


def test_health_up() -> None:
    r = parse_health(_raw("health/health_up.json"))
    assert isinstance(r, HealthReport)
    assert r.is_healthy
    assert r.timestamp == TS
    assert (r.database.status, r.database.response_time_ms, r.database.error) == (
        HealthStatus.UP,
        3,
        None,
    )
    assert r.readiness is not None
    assert r.readiness.is_ready
    assert r.served_fhir_versions == (FhirVersion.R4, FhirVersion.R5)
    assert (r.inactive_contexts.count, r.inactive_contexts.private) == (2, 1)
    item = r.inactive_contexts.items[0]
    assert (
        item.fhir_version,
        item.ig_package,
        item.ig_packages,
        item.aliases,
        item.owner,
        item.reason,
    ) == (
        "STU3",
        "old.ig#0.9.0",
        ("old.ig#0.9.0",),
        (),
        "acme",
        "fhir-version-disabled",
    )
    r4 = r.terminology_allowlist["R4"]
    assert r4.source is AllowlistSource.REGISTRY
    assert (r4.fetched_at, r4.registry_last_update, r4.servers, r4.reason) == (
        "2026-11-25T10:00:00Z",
        "2026-11-20T00:00:00Z",
        12,
        None,
    )
    r5 = r.terminology_allowlist["R5"]
    assert r5.source is AllowlistSource.BUILT_IN
    assert r5.reason == "registry unreachable"
    assert r.acl_enabled is True


def test_health_down() -> None:
    r = parse_health(_raw("health/health_down.json", 503))
    assert not r.is_healthy
    assert r.database.status is HealthStatus.DOWN
    assert r.database.error == "connection refused"
    assert r.readiness is not None
    assert not r.readiness.is_ready


def test_minimal_and_unknown_values() -> None:
    h = {"content-type": "application/json"}
    body = b'{"status":"DEGRADED","security":{"aclSecurity":"disabled"}}'
    r = parse_health(build_raw(200, h, body, build_meta(200, h, 0.0, 1)))
    assert r.status == "DEGRADED"
    assert not r.is_healthy
    assert r.timestamp is None
    assert r.readiness is None
    assert r.served_fhir_versions == ()
    assert r.acl_enabled is False
    assert r.database.status is None


# --------------------------------------------------------------------------- the 503 rule


def test_503_with_report_body_is_returned() -> None:
    raw = _raw("health/readiness_down.json", 503)
    r = finalize(raw, parse_readiness, want_raw=False, report_on_503=True)
    assert isinstance(r, ReadinessReport)
    assert not r.is_ready


@pytest.mark.parametrize(
    ("path", "content_type"),
    [("problems/not-ready.json", "application/problem+json"), (None, "application/json")],
)
def test_503_with_problem_or_empty_body_raises(path: str | None, content_type: str) -> None:
    with pytest.raises(ServiceUnavailableError):
        finalize(_raw(path, 503, content_type), parse_readiness, want_raw=False, report_on_503=True)


def test_503_report_raises_where_not_allowed() -> None:
    with pytest.raises(ServiceUnavailableError):
        finalize(_raw("health/readiness_down.json", 503), parse_readiness, want_raw=False)


def test_to_dict() -> None:
    d = parse_health(_raw("health/health_up.json")).to_dict()
    assert d["timestamp"] == "2025-10-26T08:00:00+00:00"
    assert d["served_fhir_versions"] == ["R4", "R5"]
    assert d["terminology_allowlist"]["R5"]["source"] == "built-in"
