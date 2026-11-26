"""Sans-I/O request building: every SDK operation becomes a ``RequestSpec``.

The sync and async transports turn a spec into an ``httpx`` request; nothing here does I/O.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import IO, Any
from urllib.parse import quote

from fvs_client._bodies import FileBody, MultipartFile
from fvs_client._config import Settings
from fvs_client._inputs import (
    Resource,
    check_exact_ig,
    check_include_ig,
    check_register_args,
    prepare_resource,
)
from fvs_client.errors import InputError
from fvs_client.models import (
    AccessChange,
    FhirVersion,
    IgInput,
    IgRef,
    ResultFormat,
    TerminologySettings,
    ValidationOptions,
)

__all__ = [
    "FileBody",
    "MultipartFile",
    "RequestSpec",
    "build_context_update",
    "build_dependencies",
    "build_exclude",
    "build_files",
    "build_health",
    "build_include",
    "build_liveness",
    "build_package_update",
    "build_readiness",
    "build_register",
    "build_upload",
    "build_validate",
    "default_headers",
    "join_url",
    "quote_segment",
    "request_headers",
    "request_kwargs",
]


@dataclass(frozen=True, slots=True, kw_only=True)
class RequestSpec:
    """Everything needed to send one operation.

    Attributes:
        method: HTTP method.
        path: Path relative to the base URL, already percent-encoded per segment.
        params: Query parameters (httpx encodes them; ``#`` → ``%23``, ``|`` → ``%7C``).
        accept: ``Accept`` header value.
        content: Raw body bytes, or a ``FileBody`` streamed from disk.
        content_type: ``Content-Type`` for ``content``.
        json: JSON body (sent with ``Content-Type: application/json``).
        files: Multipart file parts.
        data: Multipart form fields.
        is_admin: True for state-changing administrative operations (retry policy differs).
        report_on_503: Parse a 503 with a non-problem JSON body as a result (health endpoints).
    """

    method: str
    path: str
    params: Mapping[str, str] = field(default_factory=dict[str, str])
    accept: str = "application/json"
    content: bytes | FileBody | None = None
    content_type: str | None = None
    json: Any = None
    files: tuple[MultipartFile, ...] = ()
    data: Mapping[str, str] = field(default_factory=dict[str, str])
    is_admin: bool = False
    report_on_503: bool = False


def quote_segment(segment: str) -> str:
    """Percent-encode one path segment (``/``, ``#``, ``|`` … are all encoded)."""
    return quote(segment, safe="")


def join_url(base_url: str, path: str) -> str:
    """Join ``base_url`` (no trailing slash) and ``path`` without duplicate slashes."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def default_headers(settings: Settings, accept: str) -> dict[str, str]:
    """Headers sent on every request; ``Authorization`` only when an API key is configured."""
    headers = {**settings.headers, "User-Agent": settings.user_agent, "Accept": accept}
    if settings.api_key is not None:
        headers["Authorization"] = f"Bearer {settings.api_key.get_secret_value()}"
    return headers


def request_headers(
    settings: Settings, spec: RequestSpec, extra_headers: Mapping[str, str]
) -> tuple[str, dict[str, str]]:
    """Absolute URL and headers for ``spec`` (shared by the sync and async transports)."""
    headers = {**default_headers(settings, spec.accept), **extra_headers}
    if spec.content_type:
        headers["Content-Type"] = spec.content_type
    return join_url(settings.base_url, spec.path), headers


def request_kwargs(spec: RequestSpec, *, asynchronous: bool) -> dict[str, Any]:
    """Body keyword arguments for ``httpx.Client.build_request`` (fresh for every attempt)."""
    kwargs: dict[str, Any] = {}
    if isinstance(spec.content, FileBody):
        kwargs["content"] = spec.content.iter_async() if asynchronous else spec.content.iter_sync()
    elif spec.content is not None:
        kwargs["content"] = spec.content
    if spec.json is not None:
        kwargs["json"] = spec.json
    if spec.files:
        for part in spec.files:
            if part.handle.seekable():
                part.handle.seek(0)
        kwargs["files"] = [(p.field, (p.filename, p.handle, p.content_type)) for p in spec.files]
    if spec.data:
        kwargs["data"] = dict(spec.data)
    return kwargs


# --------------------------------------------------------------------------- validation


def build_validate(
    fhir_version: FhirVersion | str, resource: Resource, options: ValidationOptions
) -> RequestSpec:
    """``POST /{version}/validate`` with query ``ig``, ``profile``, ``tx``, ``txMode``."""
    version = FhirVersion.parse(fhir_version)
    body, content_type = prepare_resource(resource, options.content_type)
    params: dict[str, str] = {}
    if options.ig is not None:
        params["ig"] = str(options.ig)
    profiles = tuple(options.profiles)
    if profiles:
        params["profile"] = ",".join(profiles)
    if options.tx is not None:
        params["tx"] = options.tx
    if options.tx_mode is not None:
        params["txMode"] = str(options.tx_mode)
    return RequestSpec(
        method="POST",
        path=f"/{version}/validate",
        params=params,
        accept=ResultFormat.parse(options.result_format).accept,
        content=body,
        content_type=content_type,
    )


# --------------------------------------------------------------------------- validator contexts


def build_include(
    fhir_version: FhirVersion | str,
    ig: IgInput,
    *,
    shareable: bool | None,
    terminology: TerminologySettings | None,
) -> RequestSpec:
    """``POST /{version}/validator``: one IG (``igPackageId``) or two (``igPackages``)."""
    version = FhirVersion.parse(fhir_version)
    refs = check_include_ig(ig)
    body: dict[str, Any]
    if len(refs) == 1:
        body = {"igPackageId": refs[0].name}
        if refs[0].version is not None:
            body["igPackageVersion"] = refs[0].version
    else:
        body = {"igPackages": [_ig_entry(r) for r in refs]}
    if shareable is not None:
        body["shareable"] = shareable
    if terminology is not None:
        body["terminology"] = terminology.to_wire()
    return RequestSpec(method="POST", path=f"/{version}/validator", json=body, is_admin=True)


def _ig_entry(ref: IgRef) -> dict[str, str]:
    entry = {"igPackageId": ref.name}
    if ref.version is not None:
        entry["igPackageVersion"] = ref.version
    return entry


def build_exclude(fhir_version: FhirVersion | str, ig: IgInput) -> RequestSpec:
    """``DELETE /{version}/validator?ig=`` (exact ``name#version`` or a two-IG key)."""
    version = FhirVersion.parse(fhir_version)
    return RequestSpec(
        method="DELETE",
        path=f"/{version}/validator",
        params={"ig": check_exact_ig(ig)},
        is_admin=True,
    )


def build_context_update(
    fhir_version: FhirVersion | str, ig: IgInput, change: AccessChange
) -> RequestSpec:
    """``PATCH /{version}/validator?ig=`` with an ``AccessChangeRequest`` body."""
    version = FhirVersion.parse(fhir_version)
    return RequestSpec(
        method="PATCH",
        path=f"/{version}/validator",
        params={"ig": check_exact_ig(ig)},
        json=change.to_wire(),
        is_admin=True,
    )


# --------------------------------------------------------------------------- IG packages


def build_upload(filename: str, handle: IO[bytes], *, shareable: bool) -> RequestSpec:
    """``POST /igs/upload`` as ``multipart/form-data``; the archive is streamed from ``handle``."""
    return RequestSpec(
        method="POST",
        path="/igs/upload",
        files=(MultipartFile("file", filename, handle, "application/gzip"),),
        data={"shareable": "true" if shareable else "false"},
        is_admin=True,
    )


def build_register(
    name: str | None,
    version: str,
    download_url: str | None,
    *,
    include_dependencies: bool,
    shareable: bool,
) -> RequestSpec:
    """``POST /igs/register`` by ``name``/``version`` or by ``downloadUrl``."""
    check_register_args(name, version, download_url)
    body: dict[str, Any] = (
        {"name": name, "version": version} if name is not None else {"downloadUrl": download_url}
    )
    body["includeDependency"] = include_dependencies
    body["shareable"] = shareable
    return RequestSpec(method="POST", path="/igs/register", json=body, is_admin=True)


def _package_path(name: str, version: str, suffix: str = "") -> str:
    if not name or not version:
        raise InputError("Package name and version must not be empty")
    return f"/igs/{quote_segment(name)}/{quote_segment(version)}{suffix}"


def build_package_update(name: str, version: str, change: AccessChange) -> RequestSpec:
    """``PATCH /igs/{name}/{version}`` (sharing or ownership; no terminology)."""
    if change.terminology is not None:
        raise InputError("terminology applies to validator contexts only (use contexts.update)")
    return RequestSpec(
        method="PATCH", path=_package_path(name, version), json=change.to_wire(), is_admin=True
    )


def build_dependencies(name: str, version: str) -> RequestSpec:
    """``GET /igs/{name}/{version}/dependencies``."""
    return RequestSpec(method="GET", path=_package_path(name, version, "/dependencies"))


def build_files(name: str, version: str) -> RequestSpec:
    """``GET /igs/{name}/{version}/conformance`` (deprecated by the service)."""
    return RequestSpec(method="GET", path=_package_path(name, version, "/conformance"))


# --------------------------------------------------------------------------- health


def build_health() -> RequestSpec:
    """``GET /health`` (no key needed; a 503 report is a result)."""
    return RequestSpec(method="GET", path="/health", report_on_503=True)


def build_liveness() -> RequestSpec:
    """``GET /health/liveness``."""
    return RequestSpec(method="GET", path="/health/liveness")


def build_readiness() -> RequestSpec:
    """``GET /health/readiness`` (a 503 report is a result)."""
    return RequestSpec(method="GET", path="/health/readiness", report_on_503=True)
