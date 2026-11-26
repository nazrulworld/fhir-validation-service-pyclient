# Contract: `fvs_client` Public Python API (v0.1.0)

This is the SDK's outward interface. Everything not listed here is private. `AsyncClient`
mirrors `Client` exactly, with `async def` methods and `async with` support (Constitution IV).
Types are described in [../data-model.md](../data-model.md).

## Top-level exports (`fvs_client.__all__`)

- **Clients and configuration**:
  - `Client`
  - `AsyncClient`
  - `RetryConfig`
  - `__version__`
  - `SUPPORTED_API`
- **Enums**:
  - `FhirVersion`
  - `Severity`
  - `TerminologyMode`
  - `TxSource`
  - `HealthStatus`
  - `ResultFormat`
  - `RateLimitScope`
  - `ProblemType`
- **Inputs**:
  - `IgRef`
  - `ValidationOptions`
  - `TerminologySettings`
  - `AccessChange`
- **Results**:
  - `ValidationResult`
  - `ValidationIssue`
  - `OperationOutcomeResult`
  - `ValidationContextInfo`
  - `ResponseMeta`
  - `RateLimitInfo`
  - `RawResponse`
  - `IncludeResult`
  - `IncludedIg`
  - `ExcludeResult`
  - `ContextAccessResult`
  - `IgPackageResult`
  - `PackageAccessResult`
  - `PackageDependencies`
  - `PackageFiles`
  - `HealthReport`
  - `ReadinessReport`
  - `LivenessReport`
  - `Problem`
- **Errors**: see [Errors](#errors).

## Client construction

```python
Client(
    base_url: str | None = None,          # else $FVS_BASE_URL; missing → InputError
    *,
    api_key: str | None = None,           # else $FVS_API_KEY; may stay None (public mode / health)
    timeout: float | httpx.Timeout = DEFAULT_TIMEOUT,          # Timeout(60.0, connect=10.0); None is not allowed (Constitution IV)
    retries: RetryConfig | int | None = None,   # None → defaults below; int → max_retries for safe ops
    headers: Mapping[str, str] | None = None,   # extra default headers (Authorization not allowed here)
    user_agent_suffix: str | None = None,
    http_client: httpx.Client | None = None,    # caller-owned; SDK never closes it
)
```

- `RetryConfig(max_retries=2, admin_max_retries=0, backoff_base=0.5, backoff_max=8.0,
  max_retry_after=60.0)`
- `close()`, `__enter__`/`__exit__`. On `AsyncClient`: `aclose()` and `__aenter__`/
  `__aexit__`.
- `repr(client)` → `Client(base_url='https://…', api_key='**********')`; the key is never shown.

## Operations

Every operation takes these keyword-only arguments:
- `raw: bool = False`: `True` returns `RawResponse` (typed with `@overload`)
- `timeout: float | httpx.Timeout | None = None`: `None` here means "use the client's timeout". It never means "no timeout"
- `extra_headers: Mapping[str, str] | None` (a key named `Authorization`, in any case, → `InputError`)

Admin operations also take `retries: int | None` (per-call override of `admin_max_retries`).

### Validation (Story 1)

```python
client.validate(
    resource: Mapping[str, Any] | str | bytes | os.PathLike[str],
    *,
    fhir_version: FhirVersion | str,
    ig: str | IgRef | tuple[IgRef, IgRef] | None = None,
    profiles: Sequence[str] = (),
    tx: str | None = None,
    tx_mode: TerminologyMode | str | None = None,
    result_format: ResultFormat = ResultFormat.SUMMARY,
    content_type: str | None = None,
    options: ValidationOptions | None = None,   # alternative to the keywords; mixing both → InputError
    raw: bool = False, timeout=..., extra_headers=None,
) -> ValidationResult | OperationOutcomeResult | RawResponse
```

- `result_format=SUMMARY` → `ValidationResult`; an OperationOutcome format →
  `OperationOutcomeResult` (precise overloads on the `result_format` literal and `raw`).
- An invalid resource is a **result** (`valid=False`), never an exception.

```python
client.validate_many(
    resources: Iterable[<same as resource>],
    *, fhir_version, concurrency: int = 8, <same options as validate>,
) -> list[ValidationResult | OperationOutcomeResult | RawResponse | FVSError]
```

Results come back in input order; each failure (including `InputError`) is captured in its slot.

### Validator contexts (Story 4, admin): `client.contexts`

```python
client.contexts.include(
    fhir_version, ig: str | IgRef | tuple[IgRef, IgRef], *,
    shareable: bool | None = None, terminology: TerminologySettings | None = None, ...
) -> IncludeResult
client.contexts.exclude(fhir_version, ig: str | IgRef | tuple[IgRef, IgRef], ...) -> ExcludeResult
client.contexts.update(fhir_version, ig, change: AccessChange, ...) -> ContextAccessResult
```

- For `include`, the version may be exact, `latest` or a series (`1.2.x`). A single `IgRef`
  sends `igPackageId`/`igPackageVersion`; a tuple sends `igPackages`.
- `exclude` and `update` need exact `name#version` (or a two-IG key); `latest` and series are
  rejected locally.

### IG packages (Story 4): `client.packages`

```python
client.packages.upload(archive: os.PathLike[str] | BinaryIO, *, shareable: bool = True, ...) -> IgPackageResult
client.packages.register(name: str | None = None, version: str = "latest", *,
                         download_url: str | None = None, include_dependencies: bool = True,
                         shareable: bool = True, ...) -> IgPackageResult
client.packages.update(name: str, version: str, change: AccessChange, ...) -> PackageAccessResult
client.packages.dependencies(name: str, version: str, ...) -> PackageDependencies
client.packages.files(name: str, version: str, ...) -> PackageFiles
```

- `upload`, `register` and `update` are admin operations. `dependencies` and `files` are
  validate operations (safe; default retries apply).
- `upload` streams the archive.
- `register` requires exactly one of `name` and `download_url`.
- `update` must not include `terminology` (`InputError`).
- `files` is deprecated and emits a `DeprecationWarning`.

### Health (Story 5): `client.health`

```python
client.health.check(...) -> HealthReport          # 200 or 503-with-report → returned
client.health.liveness(...) -> LivenessReport
client.health.readiness(...) -> ReadinessReport   # 503-with-report → returned, is_ready=False
```

These need no API key. When a key is configured it is still sent, which is harmless.

## Errors

```text
FVSError
├── InputError(FVSError, ValueError)          # local check failed; nothing sent
├── TransportError
│   ├── FVSConnectionError
│   └── FVSTimeoutError
└── APIError                                   # .status_code .problem .problem_type .request_id .response
    ├── BadRequestError                        # 400 405 406 413 415 422 424
    │   ├── InvalidResourceError               # .issues
    │   ├── UnknownProfileError                # .unresolved_profiles
    │   └── DependencyConflictError            # .conflicts
    ├── AuthenticationError                    # 401
    ├── PermissionDeniedError                  # 403
    ├── NotFoundError                          # 404
    ├── ConflictError                          # 409
    ├── RateLimitError                         # 429 .scope .limit .retry_after
    ├── ServiceUnavailableError                # 503 .retry_after
    └── ServerError                            # 500, other 5xx, unexpected 2xx/3xx shapes
```

`str(error)` → `"<status> <problem short name>: <detail or title> (request id <id>)"`. It
never contains the API key or the resource body.

## Logging

- Logger name `fvs_client`, with a `NullHandler` attached.
- DEBUG per attempt; INFO per retry decision.
- Never logs headers, bodies or `tx` values.

## Stability

- 0.x: breaking changes are allowed but marked **BREAKING** in `CHANGELOG.md` (spec FR-026).
- Supported service API: FVS 1.0.x (documented in the README and in `fvs_client.SUPPORTED_API`).
