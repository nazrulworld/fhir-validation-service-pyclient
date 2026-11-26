"""RFC 9457 problem parsing and status → error mapping (T017)."""

from __future__ import annotations

import pytest

from fvs_client import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DependencyConflictError,
    InvalidResourceError,
    NotFoundError,
    PermissionDeniedError,
    Problem,
    ProblemType,
    RateLimitError,
    RateLimitScope,
    ServerError,
    ServiceUnavailableError,
    UnknownProfileError,
)
from fvs_client._parsing import build_meta, build_raw
from fvs_client._problems import error_for, parse_problem, short_name
from tests.fixtures import load, load_json, problem_names

PROBLEM_JSON = {"content-type": "application/problem+json"}

EXPECTED_CLASS: dict[str, type[APIError]] = {
    "invalid-request": BadRequestError,
    "invalid-resource": InvalidResourceError,
    "dependency-conflict": DependencyConflictError,
    "unknown-profile": UnknownProfileError,
    "unsupported-fhir-version": BadRequestError,
    "package-source-not-allowed": BadRequestError,
    "tx-server-not-registered": BadRequestError,
    "unauthorized": AuthenticationError,
    "forbidden": PermissionDeniedError,
    "not-found": NotFoundError,
    "package-not-found": NotFoundError,
    "method-not-allowed": BadRequestError,
    "not-acceptable": BadRequestError,
    "conflict": ConflictError,
    "alias-conflict": ConflictError,
    "package-too-large": BadRequestError,
    "payload-too-large": BadRequestError,
    "unsupported-media-type": BadRequestError,
    "package-unsafe": BadRequestError,
    "fhir-version-disabled": BadRequestError,
    "dependency-not-found": BadRequestError,
    "rate-limited": RateLimitError,
    "internal-error": ServerError,
    "not-ready": ServiceUnavailableError,
    "overloaded": ServiceUnavailableError,
    "tx-registry-unavailable": ServiceUnavailableError,
    "insufficient-capacity": ServiceUnavailableError,
}


def _raw(status: int, body: bytes, headers: dict[str, str] | None = None) -> object:
    hdrs = {"x-request-id": "req-1", **(headers if headers is not None else PROBLEM_JSON)}
    return build_raw(status, hdrs, body, build_meta(status, hdrs, 0.0, 1))


def test_catalogue_has_all_27_types() -> None:
    assert len(ProblemType) == 27
    assert sorted(p.value for p in ProblemType) == problem_names()
    assert set(EXPECTED_CLASS) == {p.value for p in ProblemType}


@pytest.mark.parametrize("name", problem_names())
def test_parse_every_fixture(name: str) -> None:
    data = load_json(f"problems/{name}.json")
    problem = parse_problem(PROBLEM_JSON, load(f"problems/{name}.json"))
    assert isinstance(problem, Problem)
    assert problem.type_uri == data["type"]
    assert problem.type == ProblemType(name)
    assert problem.status == data["status"]
    assert problem.title == data["title"]
    assert problem.correlation_id == data["correlationId"]
    assert problem.detail == data.get("detail")


def test_type_specific_members() -> None:
    p = parse_problem(PROBLEM_JSON, load("problems/rate-limited.json"))
    assert p is not None
    assert (p.scope, p.limit, p.retry_after_seconds) == (RateLimitScope.KEY, 5, 61)
    p = parse_problem(PROBLEM_JSON, load("problems/unknown-profile.json"))
    assert p is not None
    assert p.unresolved_profiles == ("http://example.org/StructureDefinition/nope",)
    p = parse_problem(PROBLEM_JSON, load("problems/invalid-resource.json"))
    assert p is not None
    assert p.issues[0].message.startswith("Unable to parse JSON")
    p = parse_problem(PROBLEM_JSON, load("problems/dependency-conflict.json"))
    assert p is not None
    assert p.conflicts == load_json("problems/dependency-conflict.json")["conflicts"]


@pytest.mark.parametrize(
    ("uri", "expected"),
    [
        (
            "https://nazrulworld.github.io/fhir-validation-service/problems/rate-limited",
            "rate-limited",
        ),
        ("https://other.host/x/problems/not-ready/", "not-ready"),
        ("urn:problem:whatever", "urn:problem:whatever"),
        ("rate-limited", "rate-limited"),
        ("", ""),
    ],
)
def test_short_name(uri: str, expected: str) -> None:
    assert short_name(uri) == expected


def test_from_uri_any_host() -> None:
    assert ProblemType.from_uri("https://a.example/problems/overloaded") is ProblemType.OVERLOADED
    assert ProblemType.from_uri("overloaded") is ProblemType.OVERLOADED
    assert ProblemType.from_uri("https://a.example/problems/brand-new") is None


def test_unknown_members_go_to_extensions_and_unknown_type_is_str() -> None:
    body = b'{"type":"https://x/problems/brand-new","title":"T","status":400,"correlationId":"c","foo":1}'
    p = parse_problem(PROBLEM_JSON, body)
    assert p is not None
    assert p.type == "brand-new"
    assert not isinstance(p.type, ProblemType)
    assert p.extensions == {"foo": 1}


def test_plain_json_with_type_and_status_is_a_problem() -> None:
    body = b'{"type":"https://x/problems/overloaded","title":"T","status":503}'
    p = parse_problem({"content-type": "application/json"}, body)
    assert p is not None
    assert p.type is ProblemType.OVERLOADED
    assert p.correlation_id is None


@pytest.mark.parametrize(
    ("headers", "body"),
    [
        ({"content-type": "text/html"}, b"<html>bad gateway</html>"),
        ({"content-type": "application/json"}, b'{"status":"DOWN"}'),
        ({"content-type": "application/problem+json"}, b"not json"),
        ({"content-type": "application/problem+json"}, b"[1, 2]"),
        ({}, b""),
    ],
)
def test_non_problem_bodies(headers: dict[str, str], body: bytes) -> None:
    assert parse_problem(headers, body) is None


@pytest.mark.parametrize("name", problem_names())
def test_status_mapping_from_fixtures(name: str) -> None:
    status = load_json(f"problems/{name}.json")["status"]
    err = error_for(_raw(status, load(f"problems/{name}.json")))  # type: ignore[arg-type]
    assert type(err) is EXPECTED_CLASS[name]
    assert err.status_code == status
    assert err.problem_type == ProblemType(name)
    assert err.request_id == "req-1"
    assert err.problem is not None


@pytest.mark.parametrize(
    ("status", "cls"),
    [
        (400, BadRequestError),
        (401, AuthenticationError),
        (403, PermissionDeniedError),
        (404, NotFoundError),
        (405, BadRequestError),
        (406, BadRequestError),
        (409, ConflictError),
        (410, APIError),
        (413, BadRequestError),
        (415, BadRequestError),
        (418, APIError),
        (422, BadRequestError),
        (424, BadRequestError),
        (429, RateLimitError),
        (500, ServerError),
        (502, ServerError),
        (503, ServiceUnavailableError),
        (504, ServerError),
        (302, ServerError),
    ],
)
def test_status_table_without_problem_body(status: int, cls: type[APIError]) -> None:
    err = error_for(_raw(status, b"<html>oops</html>", {"content-type": "text/html"}))  # type: ignore[arg-type]
    assert type(err) is cls
    assert err.problem is None
    assert err.problem_type is None
    assert err.response.text == "<html>oops</html>"


def test_400_refined_only_by_known_short_names() -> None:
    body = b'{"type":"https://x/problems/invalid-request","title":"Bad","status":400,"correlationId":"c"}'
    assert type(error_for(_raw(400, body))) is BadRequestError  # type: ignore[arg-type]


def test_str_format_with_detail_and_request_id() -> None:
    err = error_for(_raw(404, load("problems/package-not-found.json")))  # type: ignore[arg-type]
    assert (
        str(err)
        == "404 package-not-found: IG package no.such.ig#1.0.0 is not stored (request id req-1)"
    )


def test_str_format_falls_back_to_title() -> None:
    err = error_for(_raw(401, load("problems/unauthorized.json")))  # type: ignore[arg-type]
    assert str(err) == "401 unauthorized: Unauthorized (request id req-1)"


def test_str_format_without_problem_or_request_id() -> None:
    raw = build_raw(502, {}, b"<html/>", build_meta(502, {}, 0.0, 1))
    assert str(error_for(raw)) == "502 http-error: Bad Gateway"


def test_correlation_id_used_when_header_missing() -> None:
    raw = build_raw(
        404, PROBLEM_JSON, load("problems/package-not-found.json"), build_meta(404, {}, 0.0, 1)
    )
    err = error_for(raw)
    assert err.request_id == "corr-0011"
