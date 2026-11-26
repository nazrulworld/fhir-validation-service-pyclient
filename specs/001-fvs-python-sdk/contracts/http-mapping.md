# Contract: SDK operation ↔ FVS HTTP mapping

**Source of truth**: [fvs-openapi-v1.0.0.yaml](./fvs-openapi-v1.0.0.yaml) (upstream tag `v1.0.0`,
SHA-256 `a4bfd8b0…cfabe`). Contract tests assert every row below against that file.

## Common request behaviour

- Base URL plus path, with no trailing-slash duplication. Path segments (`name`, `version`) are
  encoded with `quote(seg, safe="")`.
- Headers on every request:
  - `User-Agent: fvs-client/<v> httpx/<v> python/<v>[ <suffix>]`
  - `Authorization: Bearer <key>` (only when a key is configured)
  - `Accept` as below
- `{version}` is normalised to upper case (`STU3`, `R4`, `R4B`, `R5`) after local checking.

## Operation table

| SDK method | HTTP | Request | Accept | Success → model | Safe (default retry) |
|------------|------|---------|--------|-----------------|---------------------|
| `validate` | `POST /{version}/validate` | query `ig`, `profile` (comma-joined), `tx`, `txMode`; body is the resource with `Content-Type` `application/fhir+json` or `application/fhir+xml` (or the override) | `application/json` / `application/fhir+json` / `application/fhir+xml` per `result_format` | 200 → `ValidationResult` / `OperationOutcomeResult` | yes |
| `contexts.include` | `POST /{version}/validator` | JSON `{igPackageId, igPackageVersion?, shareable?, terminology?}` or `{igPackages:[…], shareable?, terminology?}` | `application/json` | 200 → `IncludeResult` | no (admin) |
| `contexts.exclude` | `DELETE /{version}/validator?ig=` | — | `application/json` | 200 → `ExcludeResult` | no (admin) |
| `contexts.update` | `PATCH /{version}/validator?ig=` | JSON `AccessChangeRequest` (only the fields that are set) | `application/json` | 200 → `ContextAccessResult` | no (admin) |
| `packages.upload` | `POST /igs/upload` | `multipart/form-data`: `file` (streamed, `application/gzip`), `shareable` (`"true"`/`"false"`) | `application/json` | 200 → `IgPackageResult` | no (admin) |
| `packages.register` | `POST /igs/register` | JSON `{name, version, includeDependency, shareable}` or `{downloadUrl, includeDependency, shareable}` | `application/json` | 200 → `IgPackageResult` | no (admin) |
| `packages.update` | `PATCH /igs/{name}/{version}` | JSON `{shareable?, owner?}` | `application/json` | 200 → `PackageAccessResult` | no (admin) |
| `packages.dependencies` | `GET /igs/{name}/{version}/dependencies` | — | `application/json` | 200 → `PackageDependencies` | yes |
| `packages.files` (deprecated) | `GET /igs/{name}/{version}/conformance` | — | `application/json` | 200 → `PackageFiles` | yes |
| `health.check` | `GET /health` | — | `application/json` | 200/503 + JSON → `HealthReport` | yes |
| `health.liveness` | `GET /health/liveness` | — | `application/json` | 200 → `LivenessReport` | yes |
| `health.readiness` | `GET /health/readiness` | — | `application/json` | 200/503 + JSON → `ReadinessReport` | yes |
| *(not wrapped)* | `GET /metrics` | | | out of scope (spec Assumptions) | |

## Response headers consumed

| Header | Used by |
|--------|---------|
| `X-Request-Id` | `ResponseMeta.request_id` (all) |
| `RateLimit-Limit` / `-Remaining` / `-Reset` | `ResponseMeta.rate_limit` (all; normally only validation) |
| `Retry-After` | `RateLimitInfo.retry_after_seconds`, retry policy (429/503) |
| `X-Validation-Context`, `-Owner`, `-Shareable` | `ValidationContextInfo` |
| `X-Tx-Mode`, `X-Tx-Server`, `X-Tx-Source` | `ValidationContextInfo` |
| `WWW-Authenticate` | ignored (kept in `RawResponse.headers`) |

## Error mapping

Pick the class by status. Within 400, refine by problem short name.

| Status | Problem short names (wiki catalogue) | SDK error |
|--------|--------------------------------------|-----------|
| 400 | `invalid-resource` | `InvalidResourceError` |
| 400 | `unknown-profile` | `UnknownProfileError` |
| 400 | `dependency-conflict` | `DependencyConflictError` |
| 400 | `invalid-request`, `unsupported-fhir-version`, `package-source-not-allowed`, `tx-server-not-registered`, other | `BadRequestError` |
| 401 | `unauthorized` | `AuthenticationError` |
| 403 | `forbidden` | `PermissionDeniedError` |
| 404 | `not-found`, `package-not-found` | `NotFoundError` |
| 405 | `method-not-allowed` | `BadRequestError` |
| 406 | `not-acceptable` | `BadRequestError` |
| 409 | `conflict`, `alias-conflict` | `ConflictError` |
| 413 | `package-too-large`, `payload-too-large` | `BadRequestError` |
| 415 | `unsupported-media-type` | `BadRequestError` |
| 422 | `package-unsafe`, `fhir-version-disabled` | `BadRequestError` |
| 424 | `dependency-not-found` | `BadRequestError` |
| 429 | `rate-limited` | `RateLimitError` |
| 500 / other 5xx | `internal-error` | `ServerError` |
| 503 | `not-ready`, `overloaded`, `tx-registry-unavailable`, `insufficient-capacity` | `ServiceUnavailableError` |
| any other 4xx | any | `APIError` |
| `httpx.ConnectError` etc. | — | `FVSConnectionError` |
| `httpx.TimeoutException` | — | `FVSTimeoutError` |

- **Problem parsing**:
  - When `Content-Type` is `application/problem+json` (or JSON with `type` and `status`
    members), the body is parsed as a `Problem`; otherwise `problem=None`.
  - The short name is the last non-empty path segment of `type`; a value with no `/` is used
    as-is.
  - `ProblemType.from_uri` matches on the short name only (any host).
- **Health exception**: for `/health` and `/health/readiness`, a 503 with a non-problem JSON
  body is parsed as a report and returned, not raised.

## Retry decision table (research R10)

| Condition | Safe op (`max_retries`, default 2) | Admin op (`admin_max_retries`, default 0) |
|-----------|------------------------------------|-------------------------------------------|
| 429 | retry after `Retry-After` (≤ `max_retry_after`, else raise) | same, if enabled |
| 503 | retry after `Retry-After`, or backoff | same, if enabled |
| Connect error (no bytes sent) | retry with backoff | **never** |
| Read/write timeout, other errors | never | never |

## Local pre-flight checks (`InputError`, nothing sent)

| Check | Limit (from contract) |
|-------|-----------------------|
| FHIR version | STU3/R4/R4B/R5, any case |
| `ig` | ≤ 256 chars; exact versions in two-IG form; no version series on validate/exclude/update |
| `profiles` | ≤ 10 distinct; each ≤ 1024 chars |
| `tx` | ≤ 512 chars; http(s); no query, fragment or user info |
| `tx_mode` | `none` / `server` / `ecosystem`; `none` + `tx` rejected |
| `owner` | `^[A-Za-z0-9_-]{2,32}$` |
| `register` | exactly one of `name` / `download_url`; `version` ≤ 64 chars |
| `AccessChange` | at least one field; no `terminology` on package update |
| Resource | dict / str / bytes / path; str or bytes must start with `{` or `<` after whitespace, unless `content_type` is given |

Size limits (20 MB body / 50 MB upload by default) are operator-configurable and **not**
checked locally (spec Edge Cases).
