"""RFC 9457 problem parsing and HTTP status → SDK error mapping."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, TypeVar, cast

from fvs_client._headers import Headers
from fvs_client.errors import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DependencyConflictError,
    InvalidResourceError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ServiceUnavailableError,
    UnknownProfileError,
)
from fvs_client.models import (
    Problem,
    ProblemType,
    RateLimitScope,
    RawResponse,
    Severity,
    ValidationIssue,
    _problem_short_name,  # pyright: ignore[reportPrivateUsage]
)

_KNOWN_MEMBERS = frozenset(
    {
        "type",
        "title",
        "status",
        "detail",
        "correlationId",
        "issues",
        "unresolvedProfiles",
        "conflicts",
        "scope",
        "limit",
        "retryAfterSeconds",
    }
)

_STATUS_CLASS: dict[int, type[APIError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    405: BadRequestError,
    406: BadRequestError,
    409: ConflictError,
    413: BadRequestError,
    415: BadRequestError,
    422: BadRequestError,
    424: BadRequestError,
    429: RateLimitError,
    503: ServiceUnavailableError,
}

_REFINE_400: dict[ProblemType, type[APIError]] = {
    ProblemType.INVALID_RESOURCE: InvalidResourceError,
    ProblemType.UNKNOWN_PROFILE: UnknownProfileError,
    ProblemType.DEPENDENCY_CONFLICT: DependencyConflictError,
}


def short_name(type_uri: str) -> str:
    """Return the problem short name: the last non-empty path segment of ``type_uri``."""
    return _problem_short_name(type_uri)


def media_type(headers: Mapping[str, str]) -> str:
    """Return the lower-cased media type of ``Content-Type`` without parameters."""
    value = Headers(headers).get("content-type", "")
    return value.split(";", 1)[0].strip().lower()


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _str_or_none(value: Any) -> str | None:
    return value if isinstance(value, str) else None


_E = TypeVar("_E", RateLimitScope, Severity)


def _enum_or_str(cls: type[_E], value: Any) -> _E | str | None:
    if not isinstance(value, str):
        return None
    try:
        return cls(value)
    except ValueError:
        return value


def as_list(value: Any) -> list[Any]:
    """Return ``value`` if it is a JSON array, else an empty list."""
    if isinstance(value, list):
        return value  # pyright: ignore[reportUnknownVariableType]
    return []


def parse_issue(item: Any) -> ValidationIssue | None:
    """Parse one ``ValidationMessage`` object; ``None`` if it is not an object."""
    if not isinstance(item, dict):
        return None
    data = cast("dict[str, Any]", item)
    severity = _enum_or_str(Severity, data.get("severity")) or ""
    return ValidationIssue(
        severity=severity,
        location=_str_or_none(data.get("location")),
        message=str(data.get("message", "")),
    )


def parse_problem(headers: Mapping[str, str], content: bytes) -> Problem | None:
    """Parse an RFC 9457 problem body.

    Accepts ``application/problem+json``, or any JSON object with ``type`` and ``status``.
    Returns ``None`` for anything else (HTML from a proxy, health reports, empty bodies).
    """
    mtype = media_type(headers)
    if not content or not (mtype.endswith("json") or mtype == ""):
        return None
    try:
        decoded: Any = json.loads(content)
    except ValueError:
        return None
    if not isinstance(decoded, dict):
        return None
    data = cast("dict[str, Any]", decoded)
    is_problem_media = mtype == "application/problem+json"
    if not is_problem_media and not ("type" in data and "status" in data):
        return None
    type_uri = _str_or_none(data.get("type")) or "about:blank"
    name = short_name(type_uri)
    issues = tuple(
        i for i in (parse_issue(x) for x in as_list(data.get("issues"))) if i is not None
    )
    profiles = tuple(str(p) for p in as_list(data.get("unresolvedProfiles")))
    return Problem(
        type_uri=type_uri,
        type=ProblemType.from_uri(type_uri) or name,
        title=_str_or_none(data.get("title")) or "",
        status=_int_or_none(data.get("status")) or 0,
        detail=_str_or_none(data.get("detail")),
        correlation_id=_str_or_none(data.get("correlationId")),
        issues=issues,
        unresolved_profiles=profiles,
        conflicts=data.get("conflicts"),
        scope=_enum_or_str(RateLimitScope, data.get("scope")),
        limit=_int_or_none(data.get("limit")),
        retry_after_seconds=_int_or_none(data.get("retryAfterSeconds")),
        extensions={k: v for k, v in data.items() if k not in _KNOWN_MEMBERS},
    )


def error_class(status: int, problem: Problem | None) -> type[APIError]:
    """Pick the error class for ``status``, refined by problem type for 400."""
    if status == 400 and problem is not None and isinstance(problem.type, ProblemType):
        refined = _REFINE_400.get(problem.type)
        if refined is not None:
            return refined
    cls = _STATUS_CLASS.get(status)
    if cls is not None:
        return cls
    if 400 <= status < 500:
        return APIError
    return ServerError


def error_for(raw: RawResponse) -> APIError:
    """Build the typed error for a non-2xx response."""
    problem = parse_problem(raw.headers, raw.content)
    return error_class(raw.status_code, problem)(raw, problem)
