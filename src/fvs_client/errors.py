"""Errors raised by ``fvs_client``.

Every error derives from :class:`FVSError`::

    FVSError
    ├── InputError(FVSError, ValueError)     # a local check failed; nothing was sent
    ├── TransportError
    │   ├── FVSConnectionError                # could not reach the service
    │   └── FVSTimeoutError                   # the service did not answer in time
    └── APIError                              # the service answered with an error status
        ├── BadRequestError                   # 400 405 406 413 415 422 424
        │   ├── InvalidResourceError          # 400 invalid-resource (.issues)
        │   ├── UnknownProfileError           # 400 unknown-profile (.unresolved_profiles)
        │   └── DependencyConflictError       # 400 dependency-conflict (.conflicts)
        ├── AuthenticationError               # 401
        ├── PermissionDeniedError             # 403
        ├── NotFoundError                     # 404
        ├── ConflictError                     # 409
        ├── RateLimitError                    # 429 (.scope .limit .retry_after)
        ├── ServiceUnavailableError           # 503 (.retry_after)
        └── ServerError                       # 500, other 5xx, unexpected statuses

A *completed* validation of an invalid resource is **not** an error: it is a result with
``valid=False``.
"""

from __future__ import annotations

import http
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fvs_client.models import (
        Problem,
        ProblemType,
        RateLimitScope,
        RawResponse,
        ResponseMeta,
        ValidationIssue,
    )

__all__ = [
    "APIError",
    "AuthenticationError",
    "BadRequestError",
    "ConflictError",
    "DependencyConflictError",
    "FVSConnectionError",
    "FVSError",
    "FVSTimeoutError",
    "InputError",
    "InvalidResourceError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "ServerError",
    "ServiceUnavailableError",
    "TransportError",
    "UnknownProfileError",
]


class FVSError(Exception):
    """Base class of every error raised by ``fvs_client``."""


class InputError(FVSError, ValueError):
    """A local check of the arguments failed; nothing was sent to the service.

    The message names the argument and the documented limit it broke (for example "at most 10
    distinct profiles").
    """


class TransportError(FVSError):
    """The request could not be completed at the HTTP transport level.

    The original ``httpx`` exception is chained as ``__cause__``.
    """


class FVSConnectionError(TransportError):
    """The service could not be reached (DNS, refused connection, TLS, broken connection)."""


class FVSTimeoutError(TransportError):
    """The service did not answer within the configured timeout."""


def _reason(status: int) -> str:
    try:
        return http.HTTPStatus(status).phrase
    except ValueError:
        return "Unknown status"


class APIError(FVSError):
    """The service answered with an error status.

    Attributes:
        status_code: The HTTP status code.
        problem: The parsed RFC 9457 problem document, or ``None`` when the body was not one
            (for example an HTML page from a proxy).
        problem_type: The problem's short name (``ProblemType`` member, or ``str`` for a type
            this SDK version does not know), or ``None`` without a problem document.
        request_id: The ``X-Request-Id`` header, falling back to the problem's ``correlationId``.
        response: The raw response (status, headers, body).
    """

    status_code: int
    problem: Problem | None
    problem_type: ProblemType | str | None
    request_id: str | None
    response: RawResponse

    def __init__(self, response: RawResponse, problem: Problem | None = None) -> None:
        self.response = response
        self.problem = problem
        self.status_code = response.status_code
        self.problem_type = problem.type if problem is not None else None
        self.request_id = response.meta.request_id or (
            problem.correlation_id if problem is not None else None
        )
        super().__init__(self._message())

    @property
    def meta(self) -> ResponseMeta:
        """Response metadata (request id, rate-limit information, attempts)."""
        return self.response.meta

    def _message(self) -> str:
        if self.problem is not None:
            name = str(self.problem.type) or "problem"
            text = self.problem.detail or self.problem.title or _reason(self.status_code)
        else:
            name = "http-error"
            text = _reason(self.status_code)
        msg = f"{self.status_code} {name}: {text}"
        if self.request_id:
            msg += f" (request id {self.request_id})"
        return msg


class BadRequestError(APIError):
    """The request was refused as invalid.

    Statuses 400, 405, 406, 413, 415, 422 and 424. Problem types include ``invalid-request``,
    ``unsupported-fhir-version``, ``package-source-not-allowed``, ``tx-server-not-registered``,
    ``method-not-allowed``, ``not-acceptable``, ``package-too-large``, ``payload-too-large``,
    ``unsupported-media-type``, ``package-unsafe``, ``fhir-version-disabled`` and
    ``dependency-not-found``.
    """


class InvalidResourceError(BadRequestError):
    """400 ``invalid-resource``: the body is not a FHIR resource that can be parsed.

    A resource that parses but is invalid is *not* this error; it returns a result with
    ``valid=False``.

    Attributes:
        issues: Why the body could not be parsed.
    """

    @property
    def issues(self) -> tuple[ValidationIssue, ...]:
        """Parse issues reported by the service."""
        return self.problem.issues if self.problem is not None else ()


class UnknownProfileError(BadRequestError):
    """400 ``unknown-profile``: a requested profile is not defined; nothing was validated."""

    @property
    def unresolved_profiles(self) -> tuple[str, ...]:
        """The requested profile URLs that could not be resolved, in request order."""
        return self.problem.unresolved_profiles if self.problem is not None else ()


class DependencyConflictError(BadRequestError):
    """400 ``dependency-conflict``: two IGs need different versions of the same package."""

    @property
    def conflicts(self) -> Any:
        """The conflicting packages and versions, as sent by the service."""
        return self.problem.conflicts if self.problem is not None else None


class AuthenticationError(APIError):
    """401 ``unauthorized``: no valid API key (missing, malformed, unknown, revoked or expired)."""


class PermissionDeniedError(APIError):
    """403 ``forbidden``: the key's role or organisation doesn't allow this operation.

    Also raised for administrative calls from outside the operator's admin networks.
    """


class NotFoundError(APIError):
    """404 ``not-found`` / ``package-not-found``.

    A package or context the caller may not use is answered exactly like one that does not
    exist; the two cases can't be told apart.
    """


class ConflictError(APIError):
    """409 ``conflict`` / ``alias-conflict``."""


class RateLimitError(APIError):
    """429 ``rate-limited``: the key's or organisation's per-minute validation cap was reached.

    Attributes:
        scope: ``key`` or ``organisation``: which limit was reached.
        limit: The per-minute limit that was reached.
        retry_after: Seconds to wait before retrying.
    """

    @property
    def scope(self) -> RateLimitScope | str | None:
        """Which limit was reached (``key`` or ``organisation``)."""
        return self.problem.scope if self.problem is not None else None

    @property
    def limit(self) -> int | None:
        """The per-minute limit that was reached."""
        if self.problem is not None and self.problem.limit is not None:
            return self.problem.limit
        return self.meta.rate_limit.limit

    @property
    def retry_after(self) -> int | None:
        """Seconds to wait (``Retry-After``, falling back to ``retryAfterSeconds``)."""
        if self.meta.rate_limit.retry_after_seconds is not None:
            return self.meta.rate_limit.retry_after_seconds
        return self.problem.retry_after_seconds if self.problem is not None else None


class ServiceUnavailableError(APIError):
    """503: ``not-ready``, ``overloaded``, ``tx-registry-unavailable`` or ``insufficient-capacity``.

    Attributes:
        retry_after: Seconds to wait before retrying, when the service said so.
    """

    @property
    def retry_after(self) -> int | None:
        """Seconds to wait (``Retry-After``), or ``None``."""
        if self.meta.rate_limit.retry_after_seconds is not None:
            return self.meta.rate_limit.retry_after_seconds
        return self.problem.retry_after_seconds if self.problem is not None else None


class ServerError(APIError):
    """500 ``internal-error``, any other 5xx, or an unexpected non-error status shape."""
