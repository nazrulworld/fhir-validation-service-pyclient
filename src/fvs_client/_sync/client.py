"""The synchronous ``Client``."""

from __future__ import annotations

import os
import warnings
from collections.abc import Callable, Iterable, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from types import TracebackType
from typing import BinaryIO, Literal, Protocol, Self, TypeVar, overload

import httpx

from fvs_client._config import DEFAULT_TIMEOUT, check_extra_headers, check_timeout, resolve_settings
from fvs_client._inputs import (
    Resource,
    prepare_archive,
    prepare_batch,
    resolve_validation_options,
)
from fvs_client._parsing import (
    finalize,
    parse_context_access,
    parse_dependencies,
    parse_exclude,
    parse_files,
    parse_health,
    parse_ig_package,
    parse_include,
    parse_liveness,
    parse_package_access,
    parse_readiness,
    validation_parser,
)
from fvs_client._requests import (
    RequestSpec,
    build_context_update,
    build_dependencies,
    build_exclude,
    build_files,
    build_health,
    build_include,
    build_liveness,
    build_package_update,
    build_readiness,
    build_register,
    build_upload,
    build_validate,
)
from fvs_client._sync.transport import SyncTransport
from fvs_client.errors import FVSError
from fvs_client.models import (
    AccessChange,
    ContextAccessResult,
    ExcludeResult,
    FhirVersion,
    HealthReport,
    IgInput,
    IgPackageResult,
    IncludeResult,
    LivenessReport,
    OperationOutcomeResult,
    PackageAccessResult,
    PackageDependencies,
    PackageFiles,
    RawResponse,
    ReadinessReport,
    ResultFormat,
    RetryConfig,
    TerminologyMode,
    TerminologySettings,
    ValidationOptions,
    ValidationResult,
)

T = TypeVar("T")

_T = TypeVar("_T")


class _Request(Protocol):
    """The client's request entry point, handed to its sub-clients."""

    def __call__(
        self,
        spec: RequestSpec,
        parser: Callable[[RawResponse], _T],
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> _T | RawResponse: ...


class Client:
    """Synchronous client for the FHIR Validation Service.

    Args:
        base_url: Service base URL, e.g. ``https://fvs.example.org``. Defaults to the
            ``FVS_BASE_URL`` environment variable.
        api_key: API key sent as ``Authorization: Bearer``. Defaults to ``FVS_API_KEY``; may be
            omitted for health checks or a deployment with access control disabled.
        timeout: Seconds, or an ``httpx.Timeout`` bounding every phase. Default 60 s (10 s to
            connect). ``None`` is not allowed.
        retries: A ``RetryConfig``, or an ``int`` setting ``max_retries`` for safe operations.
        headers: Extra headers for every request (``Authorization`` is not allowed here).
        user_agent_suffix: Appended to the ``User-Agent`` header.
        http_client: Your own ``httpx.Client`` (proxies, custom TLS, mocking). It is used as-is
            and never closed by this client.

    Use it as a context manager, or call :meth:`close`::

        with Client("https://fvs.example.org", api_key="…") as fvs:
            ...

    Errors & retries:
        Every error derives from ``FVSError``. Local argument checks raise ``InputError``
        before anything is sent; an unreachable or slow service raises ``FVSConnectionError``
        / ``FVSTimeoutError``; an error status raises an ``APIError`` subclass carrying the
        RFC 9457 problem (``problem_type``, ``request_id``, ``response``).

        429 and 503 responses are retried, waiting ``Retry-After`` when the service gives it
        (longer than ``RetryConfig.max_retry_after`` → raised at once) and a full-jitter
        backoff otherwise. Connection failures are retried for safe operations only;
        timeouts are never retried. Safe operations (validation, health, package reads) retry
        up to ``RetryConfig.max_retries`` (default 2); administrative operations don't retry
        unless ``admin_max_retries`` or a per-call ``retries=`` says so.

    Raises:
        InputError: an argument is invalid (for example no base URL anywhere).
    """

    def __init__(
        self,
        base_url: str | None = None,
        *,
        api_key: str | None = None,
        timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,
        retries: RetryConfig | int | None = None,
        headers: Mapping[str, str] | None = None,
        user_agent_suffix: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._settings = resolve_settings(
            base_url=base_url,
            api_key=api_key,
            timeout=timeout,
            headers=headers,
            user_agent_suffix=user_agent_suffix,
            retries=retries,
        )
        self._owns_http = http_client is None
        self._http = (
            http_client
            if http_client is not None
            else httpx.Client(timeout=self._settings.timeout, follow_redirects=False)
        )
        self._transport = SyncTransport(self._http, self._settings)
        self._contexts = Contexts(self._request)
        self._packages = Packages(self._request)
        self._health = Health(self._request)

    @property
    def base_url(self) -> str:
        """The service base URL."""
        return self._settings.base_url

    @property
    def contexts(self) -> Contexts:
        """Validator-context administration (``include``, ``exclude``, ``update``)."""
        return self._contexts

    @property
    def health(self) -> Health:
        """Health, liveness and readiness checks (no API key needed)."""
        return self._health

    @property
    def packages(self) -> Packages:
        """IG package operations (``upload``, ``register``, ``update``, ``dependencies``)."""
        return self._packages

    def close(self) -> None:
        """Release network connections (a caller-supplied ``http_client`` is left open)."""
        if self._owns_http:
            self._http.close()

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def __repr__(self) -> str:
        key = "'**********'" if self._settings.api_key is not None else "None"
        return f"{type(self).__name__}(base_url={self._settings.base_url!r}, api_key={key})"

    def _request(
        self,
        spec: RequestSpec,
        parser: Callable[[RawResponse], T],
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> T | RawResponse:
        effective_timeout = self._settings.timeout if timeout is None else check_timeout(timeout)
        headers = check_extra_headers(extra_headers)
        response = self._transport.send(
            spec, timeout=effective_timeout, extra_headers=headers, retries=retries
        )
        return finalize(response, parser, want_raw=raw, report_on_503=spec.report_on_503)

    # ----------------------------------------------------------------------- validation

    @overload
    def validate(
        self,
        resource: Resource,
        *,
        fhir_version: FhirVersion | str,
        ig: IgInput | None = None,
        profiles: Sequence[str] = (),
        tx: str | None = None,
        tx_mode: TerminologyMode | str | None = None,
        result_format: ResultFormat | str = ResultFormat.SUMMARY,
        content_type: str | None = None,
        options: ValidationOptions | None = None,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RawResponse: ...

    @overload
    def validate(
        self,
        resource: Resource,
        *,
        fhir_version: FhirVersion | str,
        ig: IgInput | None = None,
        profiles: Sequence[str] = (),
        tx: str | None = None,
        tx_mode: TerminologyMode | str | None = None,
        result_format: Literal[ResultFormat.SUMMARY] = ResultFormat.SUMMARY,
        content_type: str | None = None,
        options: None = None,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ValidationResult: ...

    @overload
    def validate(
        self,
        resource: Resource,
        *,
        fhir_version: FhirVersion | str,
        ig: IgInput | None = None,
        profiles: Sequence[str] = (),
        tx: str | None = None,
        tx_mode: TerminologyMode | str | None = None,
        result_format: Literal[
            ResultFormat.OPERATION_OUTCOME_JSON, ResultFormat.OPERATION_OUTCOME_XML
        ],
        content_type: str | None = None,
        options: None = None,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> OperationOutcomeResult: ...

    @overload
    def validate(
        self,
        resource: Resource,
        *,
        fhir_version: FhirVersion | str,
        ig: IgInput | None = None,
        profiles: Sequence[str] = (),
        tx: str | None = None,
        tx_mode: TerminologyMode | str | None = None,
        result_format: ResultFormat | str = ResultFormat.SUMMARY,
        content_type: str | None = None,
        options: ValidationOptions | None = None,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ValidationResult | OperationOutcomeResult | RawResponse: ...

    def validate(
        self,
        resource: Resource,
        *,
        fhir_version: FhirVersion | str,
        ig: IgInput | None = None,
        profiles: Sequence[str] = (),
        tx: str | None = None,
        tx_mode: TerminologyMode | str | None = None,
        result_format: ResultFormat | str = ResultFormat.SUMMARY,
        content_type: str | None = None,
        options: ValidationOptions | None = None,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ValidationResult | OperationOutcomeResult | RawResponse:
        """Validate one FHIR resource.

        A completed validation is always a result, whether the resource is valid or not:
        check ``result.valid`` / ``result.errors``. Errors are raised only when the service
        refuses the request (see :mod:`fvs_client.errors`).

        Args:
            resource: A dict, a JSON or XML ``str``/``bytes``, or a path to a ``.json``/``.xml``
                file (streamed from disk).
            fhir_version: ``STU3``, ``R4``, ``R4B`` or ``R5`` (any case).
            ig: IG package to validate against: ``"name"``, ``"name#version"``,
                ``"name#latest"``, an ``IgRef``, or two exact IGs (``"a#1.0.0|b#2.0.0"`` or a
                tuple of two ``IgRef``). Default: the core specification only.
            profiles: Extra profile URLs (at most 10 distinct).
            tx: Terminology server for this request only.
            tx_mode: ``none``, ``server`` or ``ecosystem`` for this request only.
            result_format: ``SUMMARY`` (default) → ``ValidationResult``;
                ``OPERATION_OUTCOME_JSON``/``_XML`` → ``OperationOutcomeResult``.
            content_type: Override the detected ``Content-Type`` of ``resource``.
            options: A ``ValidationOptions`` instead of the keyword options above.
            raw: Return the unparsed ``RawResponse`` (error statuses still raise).
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call (``Authorization`` is not allowed).

        Returns:
            ``ValidationResult``, ``OperationOutcomeResult`` or ``RawResponse``.

        Raises:
            InputError: a local check failed; nothing was sent.
            APIError: the service refused the request (subclass per status/problem type).
            TransportError: the service could not be reached or did not answer in time.

        Example:
            >>> patient = {"resourceType": "Patient"}
            >>> result = client.validate(patient, fhir_version="R4")  # doctest: +SKIP
            >>> result.valid, [i.message for i in result.errors]  # doctest: +SKIP
        """
        opts = resolve_validation_options(
            options,
            ig=ig,
            profiles=profiles,
            tx=tx,
            tx_mode=tx_mode,
            result_format=result_format,
            content_type=content_type,
        )
        spec = build_validate(fhir_version, resource, opts)
        parser = validation_parser(ResultFormat.parse(opts.result_format))
        return self._request(spec, parser, raw=raw, timeout=timeout, extra_headers=extra_headers)

    def validate_many(
        self,
        resources: Iterable[Resource],
        *,
        fhir_version: FhirVersion | str,
        concurrency: int = 8,
        ig: IgInput | None = None,
        profiles: Sequence[str] = (),
        tx: str | None = None,
        tx_mode: TerminologyMode | str | None = None,
        result_format: ResultFormat | str = ResultFormat.SUMMARY,
        content_type: str | None = None,
        options: ValidationOptions | None = None,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> list[ValidationResult | OperationOutcomeResult | RawResponse | FVSError]:
        """Validate many resources concurrently; one outcome per input, in input order.

        Each slot holds the result (as ``validate`` would return it) or the ``FVSError`` that
        resource raised (including a per-resource ``InputError``), so one failure never stops
        the others. Unexpected non-SDK exceptions propagate. Options shared by every resource
        are checked first and raise ``InputError`` before anything is sent.

        Args:
            resources: The resources (anything ``validate`` accepts).
            fhir_version: ``STU3``, ``R4``, ``R4B`` or ``R5``.
            concurrency: Maximum requests in flight (default 8).
            ig: See ``validate``.
            profiles: See ``validate``.
            tx: See ``validate``.
            tx_mode: See ``validate``.
            result_format: See ``validate``.
            content_type: See ``validate``.
            options: See ``validate``.
            raw: See ``validate``.
            timeout: See ``validate``.
            extra_headers: See ``validate``.

        Returns:
            One ``ValidationResult`` / ``OperationOutcomeResult`` / ``RawResponse`` or
            ``FVSError`` per input, in input order.

        Raises:
            InputError: ``concurrency`` < 1 or invalid shared options; nothing was sent.
        """
        batch = prepare_batch(
            concurrency,
            fhir_version,
            options,
            ig=ig,
            profiles=profiles,
            tx=tx,
            tx_mode=tx_mode,
            result_format=result_format,
            content_type=content_type,
            timeout=timeout,
            extra_headers=extra_headers,
        )
        items = list(resources)

        def one(
            resource: Resource,
        ) -> ValidationResult | OperationOutcomeResult | RawResponse | FVSError:
            try:
                return self.validate(
                    resource,
                    fhir_version=batch.fhir_version,
                    options=batch.options,
                    raw=raw,
                    timeout=timeout,
                    extra_headers=extra_headers,
                )
            except FVSError as exc:
                return exc

        if not items:
            return []
        with ThreadPoolExecutor(max_workers=min(concurrency, len(items))) as pool:
            return list(pool.map(one, items))


class Contexts:
    """Validator-context administration: ``client.contexts`` (ADMIN key)."""

    def __init__(self, request: _Request) -> None:
        self._send = request

    @overload
    def include(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        *,
        shareable: bool | None = None,
        terminology: TerminologySettings | None = None,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> IncludeResult: ...
    @overload
    def include(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        *,
        shareable: bool | None = None,
        terminology: TerminologySettings | None = None,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> RawResponse: ...
    def include(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        *,
        shareable: bool | None = None,
        terminology: TerminologySettings | None = None,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> IncludeResult | RawResponse:
        """Include (pre-build) a validator context for one or two stored IG versions.

        Args:
            fhir_version: FHIR version of the context.
            ig: One IG (``"name"``, ``"name#1.2.0"``, ``"name#latest"``, ``"name#1.2.x"``, an
                ``IgRef``) or two (``"a#1|b#2"`` or a tuple of two ``IgRef``) for a two-IG
                context. Nothing is downloaded; the versions must be stored.
            shareable: Sharing of a newly included context (default: shareable).
            terminology: Terminology setting of the new context.
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.
            retries: Retries for this call (429/503 only); default ``admin_max_retries``.

        Returns:
            ``IncludeResult`` (or ``RawResponse``).

        Raises:
            InputError: invalid IG reference; nothing was sent.
            APIError: e.g. ``NotFoundError`` (not stored), ``ConflictError`` (alias conflict),
                ``PermissionDeniedError`` (not an ADMIN key).
        """
        spec = build_include(fhir_version, ig, shareable=shareable, terminology=terminology)
        return self._send(
            spec,
            parse_include,
            raw=raw,
            timeout=timeout,
            extra_headers=extra_headers,
            retries=retries,
        )

    @overload
    def exclude(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> ExcludeResult: ...
    @overload
    def exclude(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> RawResponse: ...
    def exclude(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> ExcludeResult | RawResponse:
        """Exclude (stop pre-building) an included validator context; the package stays stored.

        Args:
            fhir_version: FHIR version of the context.
            ig: Exact ``name#version``, or a two-IG key ``A#a|B#b``; no ``latest``/series.
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.
            retries: Retries for this call (429/503 only); default ``admin_max_retries``.

        Returns:
            ``ExcludeResult`` (or ``RawResponse``).
        """
        spec = build_exclude(fhir_version, ig)
        return self._send(
            spec,
            parse_exclude,
            raw=raw,
            timeout=timeout,
            extra_headers=extra_headers,
            retries=retries,
        )

    @overload
    def update(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        change: AccessChange,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> ContextAccessResult: ...
    @overload
    def update(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        change: AccessChange,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> RawResponse: ...
    def update(
        self,
        fhir_version: FhirVersion | str,
        ig: IgInput,
        change: AccessChange,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> ContextAccessResult | RawResponse:
        """Change sharing, ownership or terminology of an included validator context.

        Args:
            fhir_version: FHIR version of the context.
            ig: Exact ``name#version``, or a two-IG key ``A#a|B#b``.
            change: What to change (``AccessChange``).
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.
            retries: Retries for this call (429/503 only); default ``admin_max_retries``.

        Returns:
            ``ContextAccessResult`` (or ``RawResponse``).
        """
        spec = build_context_update(fhir_version, ig, change)
        return self._send(
            spec,
            parse_context_access,
            raw=raw,
            timeout=timeout,
            extra_headers=extra_headers,
            retries=retries,
        )


class Packages:
    """IG package operations: ``client.packages``."""

    def __init__(self, request: _Request) -> None:
        self._send = request

    @overload
    def upload(
        self,
        archive: os.PathLike[str] | BinaryIO,
        *,
        shareable: bool = True,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> IgPackageResult: ...
    @overload
    def upload(
        self,
        archive: os.PathLike[str] | BinaryIO,
        *,
        shareable: bool = True,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> RawResponse: ...
    def upload(
        self,
        archive: os.PathLike[str] | BinaryIO,
        *,
        shareable: bool = True,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> IgPackageResult | RawResponse:
        """Upload and store an IG package archive (``.tgz``), streamed from disk (ADMIN key).

        Args:
            archive: Path to the archive, or a file opened in binary mode.
            shareable: Sharing of the stored package (ignored if already stored).
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.
            retries: Retries for this call (429/503 only); default ``admin_max_retries``.

        Returns:
            ``IgPackageResult`` (or ``RawResponse``).
        """
        filename, handle, should_close = prepare_archive(archive)
        try:
            spec = build_upload(filename, handle, shareable=shareable)
            return self._send(
                spec,
                parse_ig_package,
                raw=raw,
                timeout=timeout,
                extra_headers=extra_headers,
                retries=retries,
            )
        finally:
            if should_close:
                handle.close()

    @overload
    def register(
        self,
        name: str | None = None,
        version: str = "latest",
        *,
        download_url: str | None = None,
        include_dependencies: bool = True,
        shareable: bool = True,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> IgPackageResult: ...
    @overload
    def register(
        self,
        name: str | None = None,
        version: str = "latest",
        *,
        download_url: str | None = None,
        include_dependencies: bool = True,
        shareable: bool = True,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> RawResponse: ...
    def register(
        self,
        name: str | None = None,
        version: str = "latest",
        *,
        download_url: str | None = None,
        include_dependencies: bool = True,
        shareable: bool = True,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> IgPackageResult | RawResponse:
        """Fetch and store an IG package from the package registry or an approved URL (ADMIN key).

        Args:
            name: Package id (exactly one of ``name`` and ``download_url``).
            version: Exact version, ``latest`` (default) or a series (``1.2.x``).
            download_url: Archive URL on a host the operator allows.
            include_dependencies: Also fetch the package's dependencies.
            shareable: Sharing of every package newly stored by this call.
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.
            retries: Retries for this call (429/503 only); default ``admin_max_retries``.

        Returns:
            ``IgPackageResult`` (or ``RawResponse``): ``version`` is the concrete version.
        """
        spec = build_register(
            name,
            version,
            download_url,
            include_dependencies=include_dependencies,
            shareable=shareable,
        )
        return self._send(
            spec,
            parse_ig_package,
            raw=raw,
            timeout=timeout,
            extra_headers=extra_headers,
            retries=retries,
        )

    @overload
    def update(
        self,
        name: str,
        version: str,
        change: AccessChange,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> PackageAccessResult: ...
    @overload
    def update(
        self,
        name: str,
        version: str,
        change: AccessChange,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> RawResponse: ...
    def update(
        self,
        name: str,
        version: str,
        change: AccessChange,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
        retries: int | None = None,
    ) -> PackageAccessResult | RawResponse:
        """Change sharing or transfer ownership of a stored IG package (ADMIN key).

        Args:
            name: Package id.
            version: Package version.
            change: ``AccessChange`` with ``shareable`` and/or ``owner`` (no ``terminology``).
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.
            retries: Retries for this call (429/503 only); default ``admin_max_retries``.

        Returns:
            ``PackageAccessResult`` (or ``RawResponse``).
        """
        spec = build_package_update(name, version, change)
        return self._send(
            spec,
            parse_package_access,
            raw=raw,
            timeout=timeout,
            extra_headers=extra_headers,
            retries=retries,
        )

    @overload
    def dependencies(
        self,
        name: str,
        version: str,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> PackageDependencies: ...
    @overload
    def dependencies(
        self,
        name: str,
        version: str,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RawResponse: ...
    def dependencies(
        self,
        name: str,
        version: str,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> PackageDependencies | RawResponse:
        """Declared dependencies of a stored IG package.

        Args:
            name: Package id.
            version: Package version.
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.

        Returns:
            ``PackageDependencies`` (or ``RawResponse``).
        """
        spec = build_dependencies(name, version)
        return self._send(
            spec, parse_dependencies, raw=raw, timeout=timeout, extra_headers=extra_headers
        )

    @overload
    def files(
        self,
        name: str,
        version: str,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> PackageFiles: ...
    @overload
    def files(
        self,
        name: str,
        version: str,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RawResponse: ...
    def files(
        self,
        name: str,
        version: str,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> PackageFiles | RawResponse:
        """File listing of a stored IG package.

        .. deprecated:: 0.1.0
            The service deprecated this operation (it is not a conformance report).

        Args:
            name: Package id.
            version: Package version.
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.

        Returns:
            ``PackageFiles`` (or ``RawResponse``).
        """
        warnings.warn(
            "packages.files() is deprecated by the FHIR Validation Service",
            DeprecationWarning,
            stacklevel=2,
        )
        spec = build_files(name, version)
        return self._send(spec, parse_files, raw=raw, timeout=timeout, extra_headers=extra_headers)


class Health:
    """Health checks: ``client.health`` (no API key needed)."""

    def __init__(self, request: _Request) -> None:
        self._send = request

    @overload
    def check(
        self,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> HealthReport: ...
    @overload
    def check(
        self,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RawResponse: ...
    def check(
        self,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> HealthReport | RawResponse:
        """Detailed health report: database, readiness, FHIR versions, terminology allowlist.

        A 503 with a report body is returned (``is_healthy`` is ``False``), not raised.

        No API key is needed.

        Args:
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.

        Returns:
            ``HealthReport`` (or ``RawResponse``).
        """
        return self._send(
            build_health(), parse_health, raw=raw, timeout=timeout, extra_headers=extra_headers
        )

    @overload
    def liveness(
        self,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LivenessReport: ...
    @overload
    def liveness(
        self,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RawResponse: ...
    def liveness(
        self,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> LivenessReport | RawResponse:
        """Liveness probe: the service process is alive.

        No API key is needed.

        Args:
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.

        Returns:
            ``LivenessReport`` (or ``RawResponse``).
        """
        return self._send(
            build_liveness(), parse_liveness, raw=raw, timeout=timeout, extra_headers=extra_headers
        )

    @overload
    def readiness(
        self,
        *,
        raw: Literal[False] = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ReadinessReport: ...
    @overload
    def readiness(
        self,
        *,
        raw: Literal[True],
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> RawResponse: ...
    def readiness(
        self,
        *,
        raw: bool = False,
        timeout: float | httpx.Timeout | None = None,
        extra_headers: Mapping[str, str] | None = None,
    ) -> ReadinessReport | RawResponse:
        """Readiness probe: can the instance serve traffic?

        A 503 with a report body is returned (``is_ready`` is ``False``), not raised.

        No API key is needed.

        Args:
            raw: Return the unparsed ``RawResponse``.
            timeout: Per-call timeout; ``None`` uses the client's.
            extra_headers: Extra headers for this call.

        Returns:
            ``ReadinessReport`` (or ``RawResponse``).
        """
        return self._send(
            build_readiness(),
            parse_readiness,
            raw=raw,
            timeout=timeout,
            extra_headers=extra_headers,
        )
