# Data Model: `fvs_client`

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

All public models live in `fvs_client.models` and are re-exported from `fvs_client`. Every model
is `@dataclass(frozen=True, slots=True, kw_only=True)` and has `to_dict() -> dict[str, Any]`.
Wire names (camelCase) are mapped to snake_case attributes. Fields marked *optional* are `None`
when the service omits them. Unknown fields are never an error: they stay available in the
model's `raw` body (FR-023, FR-030).

## Enumerations (`StrEnum`)

| Enum | Values | Notes |
|------|--------|-------|
| `FhirVersion` | `STU3`, `R4`, `R4B`, `R5` | Input accepts any case; `FhirVersion.parse("r4b")` → `R4B`. Anything else is an `InputError` (local) |
| `Severity` | `FATAL`, `ERROR`, `WARNING`, `INFORMATION` | `Severity.is_error` is true for FATAL/ERROR |
| `TerminologyMode` | `none`, `server`, `ecosystem` | |
| `TxSource` | `request`, `context` | |
| `HealthStatus` | `UP`, `DOWN` | |
| `ResultFormat` | `summary`, `operation_outcome_json`, `operation_outcome_xml` | Selects the `Accept` header |
| `RateLimitScope` | `key`, `organisation` | |
| `AllowlistSource` | `registry`, `stored-registry`, `built-in` | |
| `ContextState` | `ACTIVE`, `BUILDING`, `STALE`, `ABSENT` | Readiness per-context state |
| `ProblemType` | 27 values from FR-021a | `ProblemType.from_uri(uri)` → member or `None`. The value is the short name (`"rate-limited"`) |

Fields typed with an enum are declared as `Enum | str`. A value the service sends that the enum
doesn't know is kept as `str` (research R7).

## Shared building blocks

### `RateLimitInfo`

| Field | Type | Source |
|-------|------|--------|
| `limit` | `int \| None` | `RateLimit-Limit` |
| `remaining` | `int \| None` | `RateLimit-Remaining` |
| `reset_seconds` | `int \| None` | `RateLimit-Reset` |
| `retry_after_seconds` | `int \| None` | `Retry-After` (429/503 only) |

All fields are `None` when the key is not rate-limited.

### `ResponseMeta` (on every parsed result, `RawResponse` and `APIError`)

| Field | Type | Source |
|-------|------|--------|
| `status_code` | `int` | HTTP status |
| `request_id` | `str \| None` | `X-Request-Id` |
| `rate_limit` | `RateLimitInfo` | headers above |
| `elapsed_seconds` | `float` | client-measured, final attempt |
| `attempts` | `int` | 1 + retries performed |

### `ValidationContextInfo` (validation responses only; from headers)

| Field | Type | Source |
|-------|------|--------|
| `key` | `str` | `X-Validation-Context` (`base` or `name#version` / `A#a\|B#b`) |
| `owner` | `str \| None` | `X-Validation-Context-Owner` |
| `shareable` | `bool \| None` | `X-Validation-Context-Shareable` (`"true"`/`"false"`) |
| `tx_mode` | `TerminologyMode \| str \| None` | `X-Tx-Mode` |
| `tx_server` | `str \| None` | `X-Tx-Server` |
| `tx_source` | `TxSource \| str \| None` | `X-Tx-Source` |
| `is_base` | `bool` (property) | `key == "base"` |

### `TerminologySettings` (input and output)

| Field | Type | Rules |
|-------|------|-------|
| `mode` | `TerminologyMode` | required |
| `server` | `str \| None` | required when `mode=server`; forbidden when `mode=none`; ≤ 512 chars; http(s) base URL with no query, fragment or user info |

The rules are checked locally in `__post_init__` and raise `InputError`.

## Validation

### `ValidationOptions` (input; also accepted as keyword arguments)

| Field | Type | Rules (checked locally, FR-008) |
|-------|------|-------------------------------|
| `ig` | `str \| IgRef \| tuple[IgRef, IgRef] \| None` | Rendered string ≤ 256 chars; a two-IG form needs exact versions in both parts; version series (`1.2.x`) rejected |
| `profiles` | `Sequence[str]` | ≤ 10 distinct after trim/dedupe (order preserved); each ≤ 1024 chars; no empty items |
| `tx` | `str \| None` | ≤ 512 chars; `http`/`https` scheme; no query, fragment or user info |
| `tx_mode` | `TerminologyMode \| str \| None` | one of the 3 values; `tx` together with `none` is rejected |
| `result_format` | `ResultFormat` | default `summary` |
| `content_type` | `str \| None` | overrides input sniffing |

### `IgRef` (input helper)

| Field | Type | Rules |
|-------|------|-------|
| `name` | `str` | non-empty; no `#`, `\|`, `/` or whitespace |
| `version` | `str \| None` | `None` / `"latest"` / exact version |

`IgRef.parse("name#1.0.0")` and `str(IgRef)` round-trip.

### `ValidationIssue`

| Field | Type | Wire |
|-------|------|------|
| `severity` | `Severity \| str` | `severity` |
| `location` | `str \| None` | `location` |
| `message` | `str` | `message` |

### `ValidationResult` (default result, `Accept: application/json`)

| Field | Type | Wire |
|-------|------|------|
| `valid` | `bool` | `valid` |
| `issues` | `tuple[ValidationIssue, ...]` | `messages` |
| `fhir_version` | `FhirVersion \| str` | `fhirVersion` |
| `applied_profiles` | `tuple[str, ...]` | `appliedProfiles` |
| `ig_package` | `str \| None` | `igPackage` (null → base) |
| `ig_owner` | `str \| None` | `igOwner` |
| `ig_shareable` | `bool \| None` | `igShareable` |
| `context` | `ValidationContextInfo` | headers |
| `meta` | `ResponseMeta` | headers |
| `raw` | `Mapping[str, Any]` | body |

Helpers (FR-011):
- `errors` → FATAL + ERROR issues
- `warnings`
- `information`
- `has_errors: bool`
- `issues_by_severity(*severities)`

### `OperationOutcomeResult` (FHIR result formats)

| Field | Type | Notes |
|-------|------|-------|
| `format` | `ResultFormat` | the JSON or XML OperationOutcome format |
| `body` | `dict[str, Any] \| str` | a `dict` for JSON, `str` for XML |
| `context` | `ValidationContextInfo` | |
| `meta` | `ResponseMeta` | |
| `raw` | same as `body` | |

Helper: `has_errors` (JSON only: any `issue.severity` in {fatal, error}; for XML it raises
`NotImplementedError` with a hint to use the summary format).

## Validator contexts (admin)

### `IncludedIg`

| Field | Wire |
|-------|------|
| `ig_package_id: str` | `igPackageId` |
| `ig_package_version: str` | `igPackageVersion` |
| `requested_version: str \| None` | `requestedVersion` |

### `IncludeResult` (POST `/{version}/validator`)

Fields (type → wire name):
- `fhir_version: str` → `fhirVersion`
- `key: str` → `key.igPackage`
- `ig_packages: tuple[IncludedIg, ...]` → `igPackages`
- `aliases: tuple[str, ...]` → `aliases`
- `requested_version: str | None` → `requestedVersion`
- `revision: int | None` → `revision`
- `included: tuple[str, ...]` → `included`
- `resolved: tuple[str, ...]` → `resolved`
- `terminology: TerminologySettings | None` → `terminology`
- `owner: str | None` → `owner`
- `shareable: bool | None` → `shareable`
- `warnings: tuple[str, ...]` → `warnings`

Plus `meta` and `raw`.

### `ExcludeResult` (DELETE)

- `fhir_version`
- `revision`
- `excluded: str`
- `included: tuple[str, ...]`
- `warnings`

Plus `meta` and `raw`.

### `ContextAccessResult` (PATCH `/{version}/validator`)

- `fhir_version`
- `ig_package: str`
- `revision`
- `owner`
- `shareable`
- `terminology`
- `warnings`

Plus `meta` and `raw`.

### `AccessChange` (input for both PATCH operations)

| Field | Rules |
|-------|-------|
| `shareable: bool \| None` | |
| `owner: str \| None` | `^[A-Za-z0-9_-]{2,32}$` |
| `terminology: TerminologySettings \| None` | context PATCH only; passing it to the package PATCH is an `InputError` |

At least one field must be set (`InputError` otherwise).

## IG packages

### `IgPackageResult` (upload and register; wire `IgRegistrationResponse`)

- `name: str`
- `version: str` (concrete)
- `requested_version: str | None`
- `downloaded: bool | None`
- `owner: str | None`
- `shareable: bool | None`
- `warnings: tuple[str, ...]`

Plus `meta` and `raw`.

### `PackageAccessResult` (PATCH `/igs/{name}/{version}`)

- `name`
- `version`
- `owner`
- `shareable`
- `warnings`

Plus `meta` and `raw`.

### `PackageDependencies` (GET `/igs/{name}/{version}/dependencies`)

- `name`
- `version`
- `dependencies: tuple[str, ...]` (`name#version` strings)

Plus `meta` and `raw`.

### `PackageFiles` (deprecated GET `/conformance`, FR-018)

- `name`
- `version`
- `files: tuple[str, ...]`

Plus `meta` and `raw`. The method emits a `DeprecationWarning`.

## Health

### `LivenessReport`

- `status: HealthStatus | str`
- `timestamp: datetime` (from epoch ms, UTC)

Plus `meta` and `raw`.

### `ReadinessReport`

| Field | Type |
|-------|------|
| `status` | `HealthStatus \| str` |
| `timestamp` | `datetime \| None` |
| `catalog_revision` | `int \| None` |
| `reasons` | `tuple[str, ...]` |
| `versions` | `Mapping[str, Mapping[str, Any]]` (kept as data: the nested shape is loosely specified upstream) |
| `is_ready` | `bool` (property: `status == UP`) |

Plus `meta` and `raw`.

### `HealthReport`

| Field | Type |
|-------|------|
| `status` | `HealthStatus \| str` |
| `timestamp` | `datetime \| None` |
| `database` | `DatabaseHealth(status, response_time_ms, error)` (wire `postgres`) |
| `readiness` | `ReadinessReport \| None` |
| `served_fhir_versions` | `tuple[FhirVersion \| str, ...]` (`fhirVersions.served`) |
| `inactive_contexts` | `InactiveContexts(count, private, items: tuple[InactiveContext, ...])` |
| `terminology_allowlist` | `Mapping[str, AllowlistState(source, fetched_at, registry_last_update, servers, reason)]` |
| `acl_enabled` | `bool \| None` (`security.aclSecurity == "enabled"`) |
| `is_healthy` | `bool` (property) |

Plus `meta` and `raw`.

State rule (FR-019): a 503 response from `/health` or `/health/readiness` with a JSON body
parses into the report with `status=DOWN` and is **returned**. A 503 with a problem body
(`application/problem+json`) or no body raises `ServiceUnavailableError`.

## Raw and error types

### `RawResponse` (FR-031)

- `status_code: int`
- `headers: Mapping[str, str]` (case-insensitive, read-only)
- `content: bytes`
- `text` (property)
- `json() -> Any`
- `meta: ResponseMeta`

### `Problem` (RFC 9457 body)

| Field | Wire |
|-------|------|
| `type_uri: str` | `type` |
| `type: ProblemType \| str` | short name derived from `type` |
| `title: str` | `title` |
| `status: int` | `status` |
| `detail: str \| None` | `detail` |
| `correlation_id: str \| None` | `correlationId` |
| `issues: tuple[ValidationIssue, ...]` | `issues` |
| `unresolved_profiles: tuple[str, ...]` | `unresolvedProfiles` |
| `conflicts: Any \| None` | `conflicts` (shape not in the OpenAPI; kept as data) |
| `scope: RateLimitScope \| str \| None` | `scope` |
| `limit: int \| None` | `limit` |
| `retry_after_seconds: int \| None` | `retryAfterSeconds` |
| `extensions: Mapping[str, Any]` | any other members |

### Error hierarchy

Defined in [contracts/public-api.md](./contracts/public-api.md#errors). Status → class mapping
is in [contracts/http-mapping.md](./contracts/http-mapping.md#error-mapping).

## Relationships

```text
Client / AsyncClient
 ├─ validate(...)          → ValidationResult | OperationOutcomeResult | RawResponse
 │     ├─ ValidationIssue*      └─ ValidationContextInfo, ResponseMeta → RateLimitInfo
 ├─ validate_many(...)     → list[result | FVSError]
 ├─ contexts.include/exclude/update → IncludeResult | ExcludeResult | ContextAccessResult
 ├─ packages.upload/register/update/dependencies/files → IgPackageResult | PackageAccessResult | PackageDependencies | PackageFiles
 └─ health.check/liveness/readiness → HealthReport | LivenessReport | ReadinessReport
APIError ─ problem → Problem ─ type → ProblemType
         └ response → RawResponse
```
