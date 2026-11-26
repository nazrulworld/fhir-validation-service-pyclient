"""Sans-I/O response handling: metadata, raw responses and result parsers."""

from __future__ import annotations

import datetime as _dt
import enum
from collections.abc import Callable, Iterable, Mapping
from typing import Any, TypeVar

from fvs_client._headers import Headers
from fvs_client._problems import as_list, error_for, media_type, parse_issue
from fvs_client.errors import InputError, ServerError
from fvs_client.models import (
    AllowlistSource,
    AllowlistState,
    ContextAccessResult,
    DatabaseHealth,
    ExcludeResult,
    FhirVersion,
    HealthReport,
    HealthStatus,
    IgPackageResult,
    InactiveContext,
    InactiveContexts,
    IncludedIg,
    IncludeResult,
    LivenessReport,
    OperationOutcomeResult,
    PackageAccessResult,
    PackageDependencies,
    PackageFiles,
    RateLimitInfo,
    RawResponse,
    ReadinessReport,
    ResponseMeta,
    ResultFormat,
    TerminologyMode,
    TerminologySettings,
    TxSource,
    ValidationContextInfo,
    ValidationResult,
)

T = TypeVar("T")
E = TypeVar("E", bound=enum.Enum)

HeaderInput = Mapping[str, str] | Iterable[tuple[str, str]]


def coerce_enum(cls: type[E], value: Any) -> E | str | None:
    """Return ``cls(value)``, the value as ``str`` if the enum doesn't know it, or ``None``."""
    if value is None:
        return None
    try:
        return cls(value)
    except ValueError:
        return str(value)


def _int_header(headers: Mapping[str, str], name: str) -> int | None:
    value = headers.get(name)
    if value is None:
        return None
    try:
        return int(value.strip())
    except ValueError:
        return None


def build_meta(status: int, headers: HeaderInput, elapsed: float, attempts: int) -> ResponseMeta:
    """Build ``ResponseMeta`` from the final attempt's status and headers."""
    h = headers if isinstance(headers, Headers) else Headers(headers)
    return ResponseMeta(
        status_code=status,
        request_id=h.get("x-request-id"),
        rate_limit=RateLimitInfo(
            limit=_int_header(h, "ratelimit-limit"),
            remaining=_int_header(h, "ratelimit-remaining"),
            reset_seconds=_int_header(h, "ratelimit-reset"),
            retry_after_seconds=_int_header(h, "retry-after"),
        ),
        elapsed_seconds=elapsed,
        attempts=attempts,
    )


def build_raw(status: int, headers: HeaderInput, content: bytes, meta: ResponseMeta) -> RawResponse:
    """Build the immutable ``RawResponse``."""
    h = headers if isinstance(headers, Headers) else Headers(headers)
    return RawResponse(status_code=status, headers=h, content=content, meta=meta)


def decode_json(raw: RawResponse) -> Any:
    """Decode the body as JSON, or raise the typed error for an unexpected body."""
    try:
        return raw.json()
    except ValueError:
        # A 2xx whose body isn't JSON is an unexpected shape → ServerError.
        raise ServerError(raw) from None


def json_object(raw: RawResponse) -> dict[str, Any]:
    """Decode the body as a JSON object, or raise ``ServerError``."""
    data = decode_json(raw)
    if not isinstance(data, dict):
        raise ServerError(raw)
    return data  # pyright: ignore[reportUnknownVariableType]


def finalize(
    raw: RawResponse,
    parser: Callable[[RawResponse], T],
    *,
    want_raw: bool,
    report_on_503: bool = False,
) -> T | RawResponse:
    """Turn a raw response into the caller's result.

    * error status → raise the typed ``APIError`` (also in raw mode);
    * ``want_raw`` → return ``raw`` unparsed;
    * otherwise → ``parser(raw)``.
    """
    ok = 200 <= raw.status_code < 300
    if not ok and report_on_503 and raw.status_code == 503 and is_report(raw):
        ok = True
    if not ok:
        raise error_for(raw)
    if want_raw:
        return raw
    return parser(raw)


def is_report(raw: RawResponse) -> bool:
    """True for a 503 health/readiness report body (JSON object, not a problem document)."""
    if media_type(raw.headers) == "application/problem+json" or not raw.content:
        return False
    try:
        return isinstance(raw.json(), dict)
    except ValueError:
        return False


# --------------------------------------------------------------------------- validation


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


def _opt_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _header_bool(value: str | None) -> bool | None:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered in ("true", "false"):
        return lowered == "true"
    return None


def build_context_info(headers: HeaderInput) -> ValidationContextInfo:
    """Read the ``X-Validation-Context*`` and ``X-Tx-*`` headers."""
    h = headers if isinstance(headers, Headers) else Headers(headers)
    return ValidationContextInfo(
        key=h.get("x-validation-context", ""),
        owner=h.get("x-validation-context-owner"),
        shareable=_header_bool(h.get("x-validation-context-shareable")),
        tx_mode=coerce_enum(TerminologyMode, h.get("x-tx-mode")),
        tx_server=h.get("x-tx-server"),
        tx_source=coerce_enum(TxSource, h.get("x-tx-source")),
    )


def parse_validation(raw: RawResponse) -> ValidationResult:
    """Parse a ``ValidationResponse`` body (``Accept: application/json``)."""
    data = json_object(raw)
    issues = tuple(
        i for i in (parse_issue(m) for m in as_list(data.get("messages"))) if i is not None
    )
    return ValidationResult(
        valid=data.get("valid") is True,
        issues=issues,
        fhir_version=coerce_enum(FhirVersion, data.get("fhirVersion")),
        applied_profiles=tuple(str(p) for p in as_list(data.get("appliedProfiles"))),
        ig_package=_opt_str(data.get("igPackage")),
        ig_owner=_opt_str(data.get("igOwner")),
        ig_shareable=_opt_bool(data.get("igShareable")),
        context=build_context_info(raw.headers),
        meta=raw.meta,
        raw=data,
    )


def parse_operation_outcome(raw: RawResponse, fmt: ResultFormat) -> OperationOutcomeResult:
    """Parse an OperationOutcome body (JSON → dict, XML → str)."""
    body: dict[str, Any] | str = (
        raw.text if fmt is ResultFormat.OPERATION_OUTCOME_XML else json_object(raw)
    )
    return OperationOutcomeResult(
        format=fmt,
        body=body,
        context=build_context_info(raw.headers),
        meta=raw.meta,
        raw=body,
    )


def validation_parser(
    fmt: ResultFormat,
) -> Callable[[RawResponse], ValidationResult | OperationOutcomeResult]:
    """The parser for a validation response in ``fmt``."""
    if fmt is ResultFormat.SUMMARY:
        return parse_validation

    def parse(raw: RawResponse) -> OperationOutcomeResult:
        return parse_operation_outcome(raw, fmt)

    return parse


# --------------------------------------------------------------------------- administration


def _opt_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _strs(value: Any) -> tuple[str, ...]:
    return tuple(str(v) for v in as_list(value))


def _terminology(value: Any) -> TerminologySettings | None:
    """Parse a ``TerminologySettings`` object leniently (never raises on odd server data)."""
    if not isinstance(value, dict):
        return None
    mode = _opt_str(value.get("mode"))  # pyright: ignore[reportUnknownMemberType]
    server = _opt_str(value.get("server"))  # pyright: ignore[reportUnknownMemberType]
    if mode is None:
        return None
    try:
        return TerminologySettings(mode=mode, server=server)
    except InputError:
        settings = object.__new__(TerminologySettings)
        object.__setattr__(settings, "mode", coerce_enum(TerminologyMode, mode))
        object.__setattr__(settings, "server", server)
        return settings


def _included_ig(value: Any) -> IncludedIg | None:
    if not isinstance(value, dict):
        return None
    item: dict[str, Any] = value  # pyright: ignore[reportUnknownVariableType]
    return IncludedIg(
        ig_package_id=str(item.get("igPackageId", "")),
        ig_package_version=str(item.get("igPackageVersion", "")),
        requested_version=_opt_str(item.get("requestedVersion")),
    )


def parse_include(raw: RawResponse) -> IncludeResult:
    """Parse an ``IncludeResponse``."""
    data = json_object(raw)
    key = data.get("key")
    key_value = _opt_str(key.get("igPackage")) if isinstance(key, dict) else None  # pyright: ignore[reportUnknownMemberType]
    return IncludeResult(
        fhir_version=_opt_str(data.get("fhirVersion")),
        key=key_value or "",
        ig_packages=tuple(
            i for i in (_included_ig(x) for x in as_list(data.get("igPackages"))) if i is not None
        ),
        aliases=_strs(data.get("aliases")),
        requested_version=_opt_str(data.get("requestedVersion")),
        revision=_opt_int(data.get("revision")),
        included=_strs(data.get("included")),
        resolved=_strs(data.get("resolved")),
        terminology=_terminology(data.get("terminology")),
        owner=_opt_str(data.get("owner")),
        shareable=_opt_bool(data.get("shareable")),
        warnings=_strs(data.get("warnings")),
        meta=raw.meta,
        raw=data,
    )


def parse_exclude(raw: RawResponse) -> ExcludeResult:
    """Parse an ``ExcludeResponse``."""
    data = json_object(raw)
    return ExcludeResult(
        fhir_version=_opt_str(data.get("fhirVersion")),
        revision=_opt_int(data.get("revision")),
        excluded=_opt_str(data.get("excluded")),
        included=_strs(data.get("included")),
        warnings=_strs(data.get("warnings")),
        meta=raw.meta,
        raw=data,
    )


def parse_context_access(raw: RawResponse) -> ContextAccessResult:
    """Parse an ``IncludeAccessResponse``."""
    data = json_object(raw)
    return ContextAccessResult(
        fhir_version=_opt_str(data.get("fhirVersion")),
        ig_package=_opt_str(data.get("igPackage")),
        revision=_opt_int(data.get("revision")),
        owner=_opt_str(data.get("owner")),
        shareable=_opt_bool(data.get("shareable")),
        terminology=_terminology(data.get("terminology")),
        warnings=_strs(data.get("warnings")),
        meta=raw.meta,
        raw=data,
    )


def parse_ig_package(raw: RawResponse) -> IgPackageResult:
    """Parse an ``IgRegistrationResponse`` (upload and register)."""
    data = json_object(raw)
    return IgPackageResult(
        name=_opt_str(data.get("name")),
        version=_opt_str(data.get("version")),
        requested_version=_opt_str(data.get("requestedVersion")),
        downloaded=_opt_bool(data.get("downloaded")),
        owner=_opt_str(data.get("owner")),
        shareable=_opt_bool(data.get("shareable")),
        warnings=_strs(data.get("warnings")),
        meta=raw.meta,
        raw=data,
    )


def parse_package_access(raw: RawResponse) -> PackageAccessResult:
    """Parse an ``IgAccessResponse``."""
    data = json_object(raw)
    return PackageAccessResult(
        name=_opt_str(data.get("name")),
        version=_opt_str(data.get("version")),
        owner=_opt_str(data.get("owner")),
        shareable=_opt_bool(data.get("shareable")),
        warnings=_strs(data.get("warnings")),
        meta=raw.meta,
        raw=data,
    )


def parse_dependencies(raw: RawResponse) -> PackageDependencies:
    """Parse the dependencies graph response."""
    data = json_object(raw)
    return PackageDependencies(
        name=_opt_str(data.get("name")),
        version=_opt_str(data.get("version")),
        dependencies=_strs(data.get("dependencies")),
        meta=raw.meta,
        raw=data,
    )


def parse_files(raw: RawResponse) -> PackageFiles:
    """Parse the (deprecated) package file listing."""
    data = json_object(raw)
    return PackageFiles(
        name=_opt_str(data.get("name")),
        version=_opt_str(data.get("version")),
        files=_strs(data.get("files")),
        meta=raw.meta,
        raw=data,
    )


# --------------------------------------------------------------------------- health


def _timestamp(value: Any) -> _dt.datetime | None:
    millis = _opt_int(value)
    return None if millis is None else _dt.datetime.fromtimestamp(millis / 1000, tz=_dt.UTC)


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}  # pyright: ignore[reportUnknownVariableType]


def parse_liveness(raw: RawResponse) -> LivenessReport:
    """Parse ``GET /health/liveness``."""
    data = json_object(raw)
    return LivenessReport(
        status=coerce_enum(HealthStatus, data.get("status")),
        timestamp=_timestamp(data.get("timestamp")),
        meta=raw.meta,
        raw=data,
    )


def _readiness(data: dict[str, Any], raw: RawResponse) -> ReadinessReport:
    versions = {str(k): _obj(v) for k, v in _obj(data.get("versions")).items()}
    return ReadinessReport(
        status=coerce_enum(HealthStatus, data.get("status")),
        timestamp=_timestamp(data.get("timestamp")),
        catalog_revision=_opt_int(data.get("catalogRevision")),
        reasons=_strs(data.get("reasons")),
        versions=versions,
        meta=raw.meta,
        raw=data,
    )


def parse_readiness(raw: RawResponse) -> ReadinessReport:
    """Parse ``GET /health/readiness`` (200 or 503 with a report)."""
    return _readiness(json_object(raw), raw)


def _inactive(value: Any) -> InactiveContexts:
    data = _obj(value)
    items = tuple(
        InactiveContext(
            fhir_version=_opt_str(item.get("fhirVersion")),
            ig_package=_opt_str(item.get("igPackage")),
            ig_packages=_strs(item.get("igPackages")),
            aliases=_strs(item.get("aliases")),
            owner=_opt_str(item.get("owner")),
            reason=_opt_str(item.get("reason")),
        )
        for item in (_obj(x) for x in as_list(data.get("items")))
    )
    return InactiveContexts(
        count=_opt_int(data.get("count")) or 0,
        private=_opt_int(data.get("private")) or 0,
        items=items,
    )


def _allowlist(value: Any) -> dict[str, AllowlistState]:
    return {
        str(version): AllowlistState(
            source=coerce_enum(AllowlistSource, state.get("source")),
            fetched_at=_opt_str(state.get("fetchedAt")),
            registry_last_update=_opt_str(state.get("registryLastUpdate")),
            servers=_opt_int(state.get("servers")),
            reason=_opt_str(state.get("reason")),
        )
        for version, state in ((k, _obj(v)) for k, v in _obj(value).items())
    }


def parse_health(raw: RawResponse) -> HealthReport:
    """Parse ``GET /health`` (200 or 503 with a report)."""
    data = json_object(raw)
    postgres = _obj(data.get("postgres"))
    readiness = data.get("readiness")
    acl = _opt_str(_obj(data.get("security")).get("aclSecurity"))
    fhir_versions = _obj(data.get("fhirVersions"))
    return HealthReport(
        status=coerce_enum(HealthStatus, data.get("status")),
        timestamp=_timestamp(data.get("timestamp")),
        database=DatabaseHealth(
            status=coerce_enum(HealthStatus, postgres.get("status")),
            response_time_ms=_opt_int(postgres.get("responseTime")),
            error=_opt_str(postgres.get("error")),
        ),
        readiness=_readiness(_obj(readiness), raw) if isinstance(readiness, dict) else None,
        served_fhir_versions=tuple(
            v
            for v in (coerce_enum(FhirVersion, x) for x in as_list(fhir_versions.get("served")))
            if v is not None
        ),
        inactive_contexts=_inactive(fhir_versions.get("inactiveContexts")),
        terminology_allowlist=_allowlist(_obj(data.get("terminology")).get("allowlist")),
        acl_enabled=None if acl is None else acl == "enabled",
        meta=raw.meta,
        raw=data,
    )
