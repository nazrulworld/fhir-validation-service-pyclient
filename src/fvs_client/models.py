"""Public result, input and enum types.

Every model is an immutable dataclass (``frozen=True, slots=True, kw_only=True``) with a
``to_dict()`` method. Parsed results keep the service's original body in ``raw``, so fields this
SDK version does not model are never lost. Enum-typed fields hold a ``str`` when the service sends
a value this SDK version does not know.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import enum
import json
import re
from collections.abc import Mapping, Sequence
from typing import Any, TypeVar, cast, dataclass_transform

from fvs_client.errors import InputError

__all__ = [
    "AccessChange",
    "AllowlistSource",
    "AllowlistState",
    "ContextAccessResult",
    "ContextState",
    "DatabaseHealth",
    "ExcludeResult",
    "FhirVersion",
    "HealthReport",
    "HealthStatus",
    "IgPackageResult",
    "IgRef",
    "InactiveContext",
    "InactiveContexts",
    "IncludeResult",
    "IncludedIg",
    "LivenessReport",
    "OperationOutcomeResult",
    "PackageAccessResult",
    "PackageDependencies",
    "PackageFiles",
    "Problem",
    "ProblemType",
    "RateLimitInfo",
    "RateLimitScope",
    "RawResponse",
    "ReadinessReport",
    "ResponseMeta",
    "ResultFormat",
    "RetryConfig",
    "Severity",
    "TerminologyMode",
    "TerminologySettings",
    "TxSource",
    "ValidationContextInfo",
    "ValidationIssue",
    "ValidationOptions",
    "ValidationResult",
]

_T = TypeVar("_T")


@dataclass_transform(frozen_default=True, kw_only_default=True)
def _model(cls: type[_T]) -> type[_T]:
    """Make ``cls`` a frozen, slotted, keyword-only dataclass."""
    return dataclasses.dataclass(frozen=True, slots=True, kw_only=True)(cls)


def _plain(value: Any) -> Any:
    if isinstance(value, enum.Enum):
        return value.value
    if isinstance(value, _ToDictMixin):
        return value.to_dict()
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if isinstance(value, list | tuple):
        return [_plain(v) for v in value]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(value, _dt.datetime):
        return value.isoformat()
    return value


class _ToDictMixin:
    __slots__ = ()

    def to_dict(self) -> dict[str, Any]:
        """Return the model as plain data (enums → values, datetimes → ISO 8601 strings)."""
        fields = dataclasses.fields(cast("Any", self))
        return {f.name: _plain(getattr(self, f.name)) for f in fields}


# --------------------------------------------------------------------------- enums


class FhirVersion(enum.StrEnum):
    """FHIR release a resource is validated against."""

    STU3 = "STU3"
    R4 = "R4"
    R4B = "R4B"
    R5 = "R5"

    @classmethod
    def parse(cls, value: FhirVersion | str) -> FhirVersion:
        """Return the member for ``value`` (any case, surrounding whitespace ignored).

        Raises:
            InputError: ``value`` is not STU3, R4, R4B or R5.
        """
        if isinstance(value, FhirVersion):
            return value
        try:
            return cls(str(value).strip().upper())
        except ValueError:
            raise InputError(
                f"Unsupported FHIR version {value!r}: use one of STU3, R4, R4B or R5"
            ) from None


class Severity(enum.StrEnum):
    """Severity of a validation issue."""

    FATAL = "FATAL"
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFORMATION = "INFORMATION"

    @property
    def is_error(self) -> bool:
        """True for FATAL and ERROR."""
        return self in (Severity.FATAL, Severity.ERROR)


class HealthStatus(enum.StrEnum):
    """Overall status reported by the health endpoints."""

    UP = "UP"
    DOWN = "DOWN"


class RateLimitScope(enum.StrEnum):
    """Which per-minute limit was reached."""

    KEY = "key"
    ORGANISATION = "organisation"


def _problem_short_name(type_uri: str) -> str:
    """Last non-empty path segment of a problem ``type`` URI (the value itself without ``/``)."""
    if "/" not in type_uri:
        return type_uri
    segments = [s for s in type_uri.split("/") if s]
    return segments[-1] if segments else type_uri


class ProblemType(enum.StrEnum):
    """Every problem type the FHIR Validation Service 1.0 documents (by short name)."""

    INVALID_REQUEST = "invalid-request"
    INVALID_RESOURCE = "invalid-resource"
    DEPENDENCY_CONFLICT = "dependency-conflict"
    UNKNOWN_PROFILE = "unknown-profile"
    UNSUPPORTED_FHIR_VERSION = "unsupported-fhir-version"
    PACKAGE_SOURCE_NOT_ALLOWED = "package-source-not-allowed"
    TX_SERVER_NOT_REGISTERED = "tx-server-not-registered"
    UNAUTHORIZED = "unauthorized"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not-found"
    PACKAGE_NOT_FOUND = "package-not-found"
    METHOD_NOT_ALLOWED = "method-not-allowed"
    NOT_ACCEPTABLE = "not-acceptable"
    CONFLICT = "conflict"
    ALIAS_CONFLICT = "alias-conflict"
    PACKAGE_TOO_LARGE = "package-too-large"
    PAYLOAD_TOO_LARGE = "payload-too-large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported-media-type"
    PACKAGE_UNSAFE = "package-unsafe"
    FHIR_VERSION_DISABLED = "fhir-version-disabled"
    DEPENDENCY_NOT_FOUND = "dependency-not-found"
    RATE_LIMITED = "rate-limited"
    INTERNAL_ERROR = "internal-error"
    NOT_READY = "not-ready"
    OVERLOADED = "overloaded"
    TX_REGISTRY_UNAVAILABLE = "tx-registry-unavailable"
    INSUFFICIENT_CAPACITY = "insufficient-capacity"

    @classmethod
    def from_uri(cls, type_uri: str) -> ProblemType | None:
        """Return the member whose short name ends ``type_uri`` (any host), or ``None``."""
        try:
            return cls(_problem_short_name(type_uri))
        except ValueError:
            return None


# --------------------------------------------------------------------------- configuration


@_model
class RetryConfig(_ToDictMixin):
    """Automatic retry settings.

    Retries happen only for 429 and 503 responses (waiting ``Retry-After`` when given, else a
    full-jitter exponential backoff) and, for safe operations, for connection failures.

    Attributes:
        max_retries: Retries for safe operations (validation, health, package reads).
        admin_max_retries: Retries for administrative operations (429/503 only; never after a
            connection failure or timeout). Off by default.
        backoff_base: First backoff ceiling in seconds; doubles per attempt.
        backoff_max: Upper bound of any backoff in seconds.
        max_retry_after: Longest ``Retry-After`` the SDK will wait; a longer advised wait raises
            the error at once.
    """

    max_retries: int = 2
    admin_max_retries: int = 0
    backoff_base: float = 0.5
    backoff_max: float = 8.0
    max_retry_after: float = 60.0

    def __post_init__(self) -> None:
        for name in (
            "max_retries",
            "admin_max_retries",
            "backoff_base",
            "backoff_max",
            "max_retry_after",
        ):
            if getattr(self, name) < 0:
                raise InputError(f"RetryConfig.{name} must not be negative")


# --------------------------------------------------------------------------- response metadata


@_model
class RateLimitInfo(_ToDictMixin):
    """Rate-limit headers of a response (all ``None`` when the key is not rate limited).

    Attributes:
        limit: ``RateLimit-Limit``: the per-minute limit that leaves the least room.
        remaining: ``RateLimit-Remaining``: requests still allowed in the current minute.
        reset_seconds: ``RateLimit-Reset``: seconds until the allowance next grows.
        retry_after_seconds: ``Retry-After`` (429/503 only).
    """

    limit: int | None = None
    remaining: int | None = None
    reset_seconds: int | None = None
    retry_after_seconds: int | None = None


@_model
class ResponseMeta(_ToDictMixin):
    """Metadata of the HTTP exchange behind a result or error.

    Attributes:
        status_code: HTTP status of the final attempt.
        request_id: ``X-Request-Id`` (quote it when reporting a problem to the operator).
        rate_limit: Rate-limit headers.
        elapsed_seconds: Client-measured duration of the final attempt.
        attempts: Number of HTTP attempts (1 + retries performed).
    """

    status_code: int
    request_id: str | None
    rate_limit: RateLimitInfo
    elapsed_seconds: float
    attempts: int


def _charset(content_type: str | None) -> str:
    if content_type:
        for part in content_type.split(";")[1:]:
            name, _, value = part.strip().partition("=")
            if name.lower() == "charset" and value:
                return value.strip("\"'")
    return "utf-8"


@_model
class RawResponse(_ToDictMixin):
    """An unparsed service response, returned for ``raw=True`` and carried by every ``APIError``.

    Attributes:
        status_code: HTTP status code.
        headers: Read-only, case-insensitive response headers.
        content: Body bytes.
        meta: Request id, rate-limit information, timing and attempts.
    """

    status_code: int
    headers: Mapping[str, str]
    content: bytes
    meta: ResponseMeta

    @property
    def text(self) -> str:
        """The body decoded with the response charset (UTF-8 by default)."""
        charset = _charset(self.headers.get("content-type"))
        try:
            return self.content.decode(charset, errors="replace")
        except LookupError:
            return self.content.decode("utf-8", errors="replace")

    def json(self) -> Any:
        """The body decoded as JSON.

        Raises:
            ValueError: The body is not valid JSON.
        """
        return json.loads(self.content)


# --------------------------------------------------------------------------- problems


@_model
class ValidationIssue(_ToDictMixin):
    """One validation message.

    Attributes:
        severity: FATAL, ERROR, WARNING or INFORMATION (``str`` for an unknown value).
        location: FHIRPath-like location of the issue, when given.
        message: Human-readable message.
    """

    severity: Severity | str
    location: str | None = None
    message: str


@_model
class Problem(_ToDictMixin):
    """An RFC 9457 problem document sent with an error response.

    Attributes:
        type_uri: The ``type`` member exactly as sent (a URI).
        type: Short name of ``type_uri`` (``ProblemType`` member, or ``str`` if unknown).
        title: Short summary.
        status: HTTP status repeated in the body.
        detail: Explanation (curated, safe text).
        correlation_id: Same as the ``X-Request-Id`` header.
        issues: Parse issues (``invalid-resource`` only).
        unresolved_profiles: Profiles that could not be resolved (``unknown-profile`` only).
        conflicts: Conflicting dependencies (``dependency-conflict`` only), as sent.
        scope: Which limit was reached (``rate-limited`` only).
        limit: The per-minute limit that was reached (``rate-limited`` only).
        retry_after_seconds: Seconds to wait (``rate-limited`` only).
        extensions: Any other members of the problem document.
    """

    type_uri: str
    type: ProblemType | str
    title: str
    status: int
    detail: str | None = None
    correlation_id: str | None = None
    issues: tuple[ValidationIssue, ...] = ()
    unresolved_profiles: tuple[str, ...] = ()
    conflicts: Any = None
    scope: RateLimitScope | str | None = None
    limit: int | None = None
    retry_after_seconds: int | None = None
    extensions: Mapping[str, Any] = dataclasses.field(default_factory=dict[str, Any])


# --------------------------------------------------------------------------- validation inputs


class TerminologyMode(enum.StrEnum):
    """How codes that can't be decided from the packages are checked."""

    NONE = "none"
    SERVER = "server"
    ECOSYSTEM = "ecosystem"

    @classmethod
    def parse(cls, value: TerminologyMode | str, *, what: str = "tx_mode") -> TerminologyMode:
        """Return the member for ``value`` (any case).

        Raises:
            InputError: not one of none, server, ecosystem.
        """
        if isinstance(value, TerminologyMode):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            raise InputError(
                f"Unknown {what} {value!r}: use one of none, server or ecosystem"
            ) from None


class TxSource(enum.StrEnum):
    """Where the terminology setting of a validation came from."""

    REQUEST = "request"
    CONTEXT = "context"


class ResultFormat(enum.StrEnum):
    """What ``validate`` returns (selects the ``Accept`` header)."""

    SUMMARY = "summary"
    """``ValidationResult`` (``Accept: application/json``)."""
    OPERATION_OUTCOME_JSON = "operation_outcome_json"
    """``OperationOutcomeResult`` with a dict body (``Accept: application/fhir+json``)."""
    OPERATION_OUTCOME_XML = "operation_outcome_xml"
    """``OperationOutcomeResult`` with a str body (``Accept: application/fhir+xml``)."""

    @property
    def accept(self) -> str:
        """The ``Accept`` header value for this format."""
        return _ACCEPT[self]

    @classmethod
    def parse(cls, value: ResultFormat | str) -> ResultFormat:
        """Return the member for ``value``.

        Raises:
            InputError: unknown format.
        """
        if isinstance(value, ResultFormat):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            raise InputError(
                f"Unknown result_format {value!r}: use summary, operation_outcome_json or "
                "operation_outcome_xml"
            ) from None


_ACCEPT = {
    ResultFormat.SUMMARY: "application/json",
    ResultFormat.OPERATION_OUTCOME_JSON: "application/fhir+json",
    ResultFormat.OPERATION_OUTCOME_XML: "application/fhir+xml",
}

_MAX_TX = 512
_MAX_IG = 256
_MAX_PROFILES = 10
_MAX_PROFILE_LEN = 1024
_FORBIDDEN_IG_CHARS = frozenset("#|/")


def _check_http_base_url(value: str, what: str) -> str:
    from urllib.parse import urlsplit  # noqa: PLC0415 - only needed for this check

    if not isinstance(value, str) or not value.strip():  # pyright: ignore[reportUnnecessaryIsInstance]
        raise InputError(f"{what} must be a non-empty http(s) base URL")
    if len(value) > _MAX_TX:
        raise InputError(f"{what} must be at most {_MAX_TX} characters")
    parts = urlsplit(value)
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise InputError(f"{what} must be an http(s) base URL")
    if parts.query or parts.fragment or "?" in value or "#" in value:
        raise InputError(f"{what} must not contain a query or fragment")
    if parts.username is not None or parts.password is not None:
        raise InputError(f"{what} must not contain user info")
    return value


def _bad_ig_token(value: str) -> bool:
    return not value or any(c.isspace() or c in _FORBIDDEN_IG_CHARS for c in value)


@dataclasses.dataclass(frozen=True, slots=True)
class IgRef(_ToDictMixin):
    """Reference to an Implementation Guide package: ``name`` or ``name#version``.

    Args:
        name: Package id, e.g. ``hl7.fhir.us.core``.
        version: ``None`` (highest available), ``"latest"``, an exact version, or, where an
            operation allows it, a version series such as ``1.2.x``.

    Raises:
        InputError: the name or version contains ``#``, ``|``, ``/`` or whitespace, or is empty.
    """

    name: str
    version: str | None = None

    def __post_init__(self) -> None:
        if _bad_ig_token(self.name):
            raise InputError(
                f"IG package name {self.name!r} must be non-empty without '#', '|', '/' or spaces"
            )
        if self.version is not None and _bad_ig_token(self.version):
            raise InputError(
                f"IG package version {self.version!r} must be non-empty without '#', '|', '/' "
                "or spaces"
            )

    @classmethod
    def parse(cls, text: str) -> IgRef:
        """Parse ``name`` or ``name#version``."""
        name, sep, version = text.strip().partition("#")
        return cls(name, version if sep else None)

    @property
    def is_series(self) -> bool:
        """True for a version series such as ``1.2.x``."""
        return self.version is not None and any(p in ("x", "X") for p in self.version.split("."))

    @property
    def is_exact(self) -> bool:
        """True for an exact version (not ``None``, ``latest`` or a series)."""
        return self.version is not None and self.version != "latest" and not self.is_series

    def __str__(self) -> str:
        return self.name if self.version is None else f"{self.name}#{self.version}"


IgInput = str | IgRef | tuple[IgRef, IgRef]


def _render_ig(ig: IgInput | None) -> str | None:
    """Render and check the ``ig`` query value of a validation request."""
    if ig is None:
        return None
    refs: tuple[IgRef, ...]
    if isinstance(ig, IgRef):
        refs = (ig,)
    elif isinstance(ig, tuple):
        refs = ig
    else:
        if not ig.strip():
            raise InputError("ig must not be empty")
        refs = tuple(IgRef.parse(p) for p in ig.split("|"))
    if len(refs) not in (1, 2) or not all(isinstance(r, IgRef) for r in refs):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise InputError("ig must name one IG package, or exactly two as name#version|name#version")
    if len(refs) == 2 and not all(r.is_exact for r in refs):
        raise InputError("A two-IG reference needs exact versions in both parts")
    if any(r.is_series for r in refs):
        raise InputError(
            "ig must not use a version series (e.g. 1.2.x): use the exact version, 'latest' or "
            "no version"
        )
    rendered = "|".join(str(r) for r in refs)
    if len(rendered) > _MAX_IG:
        raise InputError(f"ig must be at most {_MAX_IG} characters")
    return rendered


def _check_profiles(profiles: Sequence[str]) -> tuple[str, ...]:
    if isinstance(profiles, str):
        raise InputError("profiles must be a sequence of URLs, not a single string")
    seen: dict[str, None] = {}
    for item in profiles:
        url = item.strip()
        if not url:
            raise InputError("profiles must not contain empty items")
        if len(url) > _MAX_PROFILE_LEN:
            raise InputError(f"Each profile URL must be at most {_MAX_PROFILE_LEN} characters")
        seen.setdefault(url, None)
    if len(seen) > _MAX_PROFILES:
        raise InputError(f"At most {_MAX_PROFILES} distinct profiles are allowed per request")
    return tuple(seen)


@_model
class TerminologySettings(_ToDictMixin):
    """Terminology setting of a validator context.

    Attributes:
        mode: ``none``, ``server`` or ``ecosystem``.
        server: Base URL of the terminology server: required for ``server``, optional for
            ``ecosystem``, not allowed for ``none``; at most 512 characters.
    """

    mode: TerminologyMode | str
    server: str | None = None

    def __post_init__(self) -> None:
        mode = TerminologyMode.parse(self.mode, what="terminology mode")
        object.__setattr__(self, "mode", mode)
        if mode is TerminologyMode.SERVER and self.server is None:
            raise InputError("A terminology server is required when mode is 'server'")
        if mode is TerminologyMode.NONE and self.server is not None:
            raise InputError("A terminology server is not allowed when mode is 'none'")
        if self.server is not None:
            _check_http_base_url(self.server, "terminology server")

    def to_wire(self) -> dict[str, str]:
        """The JSON object the service expects."""
        wire = {"mode": str(self.mode)}
        if self.server is not None:
            wire["server"] = self.server
        return wire


@_model
class ValidationOptions(_ToDictMixin):
    """Options of one validation request (alternative to ``validate`` keyword arguments).

    All rules are checked on construction (``InputError``); values are normalised:
    ``ig`` becomes its query string, ``profiles`` a de-duplicated tuple, ``tx_mode`` and
    ``result_format`` enum members.

    Attributes:
        ig: One IG (``name``, ``name#version``, ``name#latest``, ``IgRef``) or two exact ones
            (``"a#1|b#2"`` or a tuple of two ``IgRef``); at most 256 characters; no series.
        profiles: Extra profile URLs: at most 10 distinct, each at most 1024 characters.
        tx: Terminology server for this request only (http(s) base URL, ≤ 512 characters).
        tx_mode: ``none``, ``server`` or ``ecosystem`` for this request only.
        result_format: What to return (default ``ResultFormat.SUMMARY``).
        content_type: Override the detected ``Content-Type`` of the resource.
    """

    ig: IgInput | None = None
    profiles: Sequence[str] = ()
    tx: str | None = None
    tx_mode: TerminologyMode | str | None = None
    result_format: ResultFormat | str = ResultFormat.SUMMARY
    content_type: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "ig", _render_ig(self.ig))
        object.__setattr__(self, "profiles", _check_profiles(self.profiles))
        if self.tx is not None:
            _check_http_base_url(self.tx, "tx")
        mode = None if self.tx_mode is None else TerminologyMode.parse(self.tx_mode)
        object.__setattr__(self, "tx_mode", mode)
        if mode is TerminologyMode.NONE and self.tx is not None:
            raise InputError("tx cannot be combined with tx_mode 'none'")
        object.__setattr__(self, "result_format", ResultFormat.parse(self.result_format))


# --------------------------------------------------------------------------- validation results


@_model
class ValidationContextInfo(_ToDictMixin):
    """Which validator context and terminology setting the service used (response headers).

    Attributes:
        key: ``X-Validation-Context``: ``base`` (core only), ``name#version`` or ``A#a|B#b``.
        owner: ``X-Validation-Context-Owner``: owning organisation's short name.
        shareable: ``X-Validation-Context-Shareable``.
        tx_mode: ``X-Tx-Mode``.
        tx_server: ``X-Tx-Server``.
        tx_source: ``X-Tx-Source``: ``request`` or ``context``.
    """

    key: str
    owner: str | None = None
    shareable: bool | None = None
    tx_mode: TerminologyMode | str | None = None
    tx_server: str | None = None
    tx_source: TxSource | str | None = None

    @property
    def is_base(self) -> bool:
        """True when the core specification alone was used."""
        return self.key == "base"


@_model
class ValidationResult(_ToDictMixin):
    """Result of a completed validation (``ResultFormat.SUMMARY``).

    An invalid resource is a result with ``valid=False``, never an exception.

    Attributes:
        valid: False when any FATAL/ERROR issue was found.
        issues: Every validation message, in service order.
        fhir_version: FHIR version validated against.
        applied_profiles: Profiles resolved and applied (requested ones first).
        ig_package: Concrete IG package (``name#version``), or ``None`` for the core context.
        ig_owner: Organisation owning the validator context.
        ig_shareable: Whether the validator context is shareable.
        context: Validator context and terminology setting used (from headers).
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    valid: bool
    issues: tuple[ValidationIssue, ...]
    fhir_version: FhirVersion | str | None
    applied_profiles: tuple[str, ...]
    ig_package: str | None
    ig_owner: str | None
    ig_shareable: bool | None
    context: ValidationContextInfo
    meta: ResponseMeta
    raw: Mapping[str, Any]

    def issues_by_severity(self, *severities: Severity | str) -> tuple[ValidationIssue, ...]:
        """Issues whose severity is one of ``severities``."""
        wanted = {str(s) for s in severities}
        return tuple(i for i in self.issues if str(i.severity) in wanted)

    @property
    def errors(self) -> tuple[ValidationIssue, ...]:
        """FATAL and ERROR issues."""
        return self.issues_by_severity(Severity.FATAL, Severity.ERROR)

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        """WARNING issues."""
        return self.issues_by_severity(Severity.WARNING)

    @property
    def information(self) -> tuple[ValidationIssue, ...]:
        """INFORMATION issues."""
        return self.issues_by_severity(Severity.INFORMATION)

    @property
    def has_errors(self) -> bool:
        """True when any FATAL or ERROR issue exists."""
        return bool(self.errors)


@_model
class OperationOutcomeResult(_ToDictMixin):
    """Result of a completed validation as a FHIR OperationOutcome.

    Attributes:
        format: ``OPERATION_OUTCOME_JSON`` or ``OPERATION_OUTCOME_XML``.
        body: The OperationOutcome: a ``dict`` for JSON, a ``str`` for XML.
        context: Validator context and terminology setting used (from headers).
        meta: Request id, rate-limit information, timing, attempts.
        raw: Same as ``body``.
    """

    format: ResultFormat
    body: dict[str, Any] | str
    context: ValidationContextInfo
    meta: ResponseMeta
    raw: dict[str, Any] | str

    @property
    def has_errors(self) -> bool:
        """True when any issue has severity ``fatal`` or ``error`` (JSON format only).

        Raises:
            NotImplementedError: for the XML format; use the summary or JSON format instead.
        """
        if isinstance(self.body, str):
            raise NotImplementedError(
                "has_errors needs a parsed body: use the summary or OPERATION_OUTCOME_JSON format"
            )
        issues: Any = self.body.get("issue", [])
        if not isinstance(issues, list):
            return False
        return any(
            isinstance(i, dict) and i.get("severity") in ("fatal", "error")  # pyright: ignore[reportUnknownMemberType]
            for i in issues  # pyright: ignore[reportUnknownVariableType]
        )


# --------------------------------------------------------------------------- administration

_OWNER_RE = re.compile(r"^[A-Za-z0-9_-]{2,32}$")


@_model
class AccessChange(_ToDictMixin):
    """A change of sharing, ownership or terminology (``contexts.update`` / ``packages.update``).

    At least one field must be set. Ownership transfers are for system-organisation
    administrators only; ``terminology`` applies to validator contexts only.

    Attributes:
        shareable: Make usable by every caller (``True``) or by the owner only (``False``).
        owner: Short name of the organisation to transfer ownership to
            (``^[A-Za-z0-9_-]{2,32}$``).
        terminology: New terminology setting of a validator context (no rebuild).
    """

    shareable: bool | None = None
    owner: str | None = None
    terminology: TerminologySettings | None = None

    def __post_init__(self) -> None:
        if self.shareable is None and self.owner is None and self.terminology is None:
            raise InputError("AccessChange needs at least one of shareable, owner, terminology")
        if self.owner is not None and not _OWNER_RE.fullmatch(self.owner):
            raise InputError(f"owner {self.owner!r} must be 2-32 letters, digits, '_' or '-'")

    def to_wire(self) -> dict[str, Any]:
        """The JSON object the service expects (only the fields that are set)."""
        wire: dict[str, Any] = {}
        if self.terminology is not None:
            wire["terminology"] = self.terminology.to_wire()
        if self.shareable is not None:
            wire["shareable"] = self.shareable
        if self.owner is not None:
            wire["owner"] = self.owner
        return wire


@_model
class IncludedIg(_ToDictMixin):
    """One IG of a validator context, with its concrete version.

    Attributes:
        ig_package_id: Package id.
        ig_package_version: Concrete version included.
        requested_version: The value the request gave (two-IG includes only).
    """

    ig_package_id: str
    ig_package_version: str
    requested_version: str | None = None


@_model
class IncludeResult(_ToDictMixin):
    """Result of ``contexts.include`` (``POST /{version}/validator``).

    Attributes:
        fhir_version: FHIR version of the context.
        key: Context key: ``name#version``, or ``A#a|B#b`` for a two-IG context.
        ig_packages: The context's IGs with concrete versions, in key order.
        aliases: Other values that find this context (two-IG contexts).
        requested_version: The version the request gave (single-IG includes).
        revision: Configuration revision committed.
        included: IG versions now included for this FHIR version.
        resolved: Every package of the context (IGs, dependencies, core).
        terminology: The context's terminology setting.
        owner: Owning organisation (may be another one if it was already included).
        shareable: Whether the context is shareable.
        warnings: Non-fatal notes from the service.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    fhir_version: str | None
    key: str
    ig_packages: tuple[IncludedIg, ...]
    aliases: tuple[str, ...]
    requested_version: str | None
    revision: int | None
    included: tuple[str, ...]
    resolved: tuple[str, ...]
    terminology: TerminologySettings | None
    owner: str | None
    shareable: bool | None
    warnings: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class ExcludeResult(_ToDictMixin):
    """Result of ``contexts.exclude`` (``DELETE /{version}/validator``).

    Attributes:
        fhir_version: FHIR version of the context.
        revision: Configuration revision committed.
        excluded: The context key that was excluded.
        included: IG versions still included for this FHIR version.
        warnings: Non-fatal notes from the service.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    fhir_version: str | None
    revision: int | None
    excluded: str | None
    included: tuple[str, ...]
    warnings: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class ContextAccessResult(_ToDictMixin):
    """Result of ``contexts.update`` (``PATCH /{version}/validator``).

    Attributes:
        fhir_version: FHIR version of the context.
        ig_package: The context key.
        revision: Configuration revision committed.
        owner: Owning organisation after the change.
        shareable: Sharing after the change.
        terminology: Terminology setting after the change.
        warnings: Non-fatal notes from the service.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    fhir_version: str | None
    ig_package: str | None
    revision: int | None
    owner: str | None
    shareable: bool | None
    terminology: TerminologySettings | None
    warnings: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class IgPackageResult(_ToDictMixin):
    """Result of ``packages.upload`` and ``packages.register``.

    Attributes:
        name: Package id.
        version: Concrete version stored or returned.
        requested_version: The version the request gave (register by name only).
        downloaded: True when the archive was fetched in this call.
        owner: Owning organisation of the stored package.
        shareable: Sharing of the stored package (unchanged if it was already stored).
        warnings: Non-fatal notes from the service.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    name: str | None
    version: str | None
    requested_version: str | None
    downloaded: bool | None
    owner: str | None
    shareable: bool | None
    warnings: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class PackageAccessResult(_ToDictMixin):
    """Result of ``packages.update`` (``PATCH /igs/{name}/{version}``).

    Attributes:
        name: Package id.
        version: Package version.
        owner: Owning organisation after the change.
        shareable: Sharing after the change.
        warnings: Non-fatal notes from the service.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    name: str | None
    version: str | None
    owner: str | None
    shareable: bool | None
    warnings: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class PackageDependencies(_ToDictMixin):
    """Declared dependencies of a stored IG package.

    Attributes:
        name: Package id.
        version: Package version.
        dependencies: Declared dependencies as ``name#version`` strings.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    name: str | None
    version: str | None
    dependencies: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class PackageFiles(_ToDictMixin):
    """Files of a stored IG package (deprecated service operation).

    Attributes:
        name: Package id.
        version: Package version.
        files: File paths inside the package.
        meta: Request id, rate-limit information, timing, attempts.
        raw: The response body exactly as received.
    """

    name: str | None
    version: str | None
    files: tuple[str, ...]
    meta: ResponseMeta
    raw: Mapping[str, Any]


# --------------------------------------------------------------------------- health


class AllowlistSource(enum.StrEnum):
    """Where a FHIR version's terminology-server allowlist came from."""

    REGISTRY = "registry"
    STORED_REGISTRY = "stored-registry"
    BUILT_IN = "built-in"


class ContextState(enum.StrEnum):
    """Build state of a validator context in a readiness report."""

    ACTIVE = "ACTIVE"
    BUILDING = "BUILDING"
    STALE = "STALE"
    ABSENT = "ABSENT"


@_model
class LivenessReport(_ToDictMixin):
    """``GET /health/liveness``: the process is alive (never depends on dependencies).

    Attributes:
        status: ``UP``.
        timestamp: Server time (UTC).
        meta: Request id, timing, attempts.
        raw: The response body exactly as received.
    """

    status: HealthStatus | str | None
    timestamp: _dt.datetime | None
    meta: ResponseMeta
    raw: Mapping[str, Any]


@_model
class ReadinessReport(_ToDictMixin):
    """``GET /health/readiness``: can this instance serve traffic?

    A not-ready service (503 with this report) is returned, not raised: check ``is_ready``.

    Attributes:
        status: ``UP`` or ``DOWN``.
        timestamp: Server time (UTC).
        catalog_revision: Package catalog revision this instance has loaded.
        reasons: Why the instance is not ready.
        versions: Per FHIR version: revisions, the base context and every shareable IG context
            (kept as data; see the service documentation for the shape).
        meta: Request id, timing, attempts.
        raw: The response body exactly as received.
    """

    status: HealthStatus | str | None
    timestamp: _dt.datetime | None
    catalog_revision: int | None
    reasons: tuple[str, ...]
    versions: Mapping[str, Mapping[str, Any]]
    meta: ResponseMeta
    raw: Mapping[str, Any]

    @property
    def is_ready(self) -> bool:
        """True when ``status`` is ``UP``."""
        return self.status == HealthStatus.UP


@_model
class DatabaseHealth(_ToDictMixin):
    """Database part of a health report.

    Attributes:
        status: ``UP`` or ``DOWN``.
        response_time_ms: Probe time in milliseconds.
        error: Error text when down.
    """

    status: HealthStatus | str | None = None
    response_time_ms: int | None = None
    error: str | None = None


@_model
class InactiveContext(_ToDictMixin):
    """A stored validator context that is not active (its FHIR version is not enabled).

    Attributes:
        fhir_version: FHIR version of the context.
        ig_package: Context key.
        ig_packages: The context's IGs (``name#version``) in key order.
        aliases: Other values that find this context.
        owner: Owning organisation.
        reason: Why it is inactive (``fhir-version-disabled``).
    """

    fhir_version: str | None
    ig_package: str | None
    ig_packages: tuple[str, ...]
    aliases: tuple[str, ...]
    owner: str | None
    reason: str | None


@_model
class InactiveContexts(_ToDictMixin):
    """Summary of inactive validator contexts.

    Attributes:
        count: All inactive contexts.
        private: Inactive private contexts (counted, never listed).
        items: The first 100 shareable inactive contexts.
    """

    count: int = 0
    private: int = 0
    items: tuple[InactiveContext, ...] = ()


@_model
class AllowlistState(_ToDictMixin):
    """Terminology-server allowlist state of one FHIR version.

    Attributes:
        source: ``registry``, ``stored-registry`` or ``built-in``.
        fetched_at: When the registry list was fetched.
        registry_last_update: The registry's own last-update time.
        servers: Number of allowed servers.
        reason: Why a fallback source is used.
    """

    source: AllowlistSource | str | None
    fetched_at: str | None
    registry_last_update: str | None
    servers: int | None
    reason: str | None


@_model
class HealthReport(_ToDictMixin):
    """``GET /health``: detailed health report.

    An unhealthy service (503 with this report) is returned, not raised: check ``is_healthy``.

    Attributes:
        status: ``UP`` or ``DOWN``.
        timestamp: Server time (UTC).
        database: Database connectivity.
        readiness: The readiness report.
        served_fhir_versions: FHIR versions this deployment serves.
        inactive_contexts: Stored contexts that are inactive.
        terminology_allowlist: Per FHIR version, the terminology allowlist state.
        acl_enabled: Whether API-key access control is enabled (``False`` in public mode).
        meta: Request id, timing, attempts.
        raw: The response body exactly as received.
    """

    status: HealthStatus | str | None
    timestamp: _dt.datetime | None
    database: DatabaseHealth
    readiness: ReadinessReport | None
    served_fhir_versions: tuple[FhirVersion | str, ...]
    inactive_contexts: InactiveContexts
    terminology_allowlist: Mapping[str, AllowlistState]
    acl_enabled: bool | None
    meta: ResponseMeta
    raw: Mapping[str, Any]

    @property
    def is_healthy(self) -> bool:
        """True when ``status`` is ``UP``."""
        return self.status == HealthStatus.UP
