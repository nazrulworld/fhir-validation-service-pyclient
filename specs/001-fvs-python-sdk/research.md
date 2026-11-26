# Research: FHIR Validation Service Python SDK (`fvs_client`)

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md) | **Date**: 2026-11-26

Every Technical Context unknown is resolved below. Versions were checked on PyPI and
endoflife.date on 2026-11-26.

## R1. Service contract source and pinning

- **Decision**: Pin the upstream OpenAPI document at release tag `v1.0.0`
  (`contracts/fvs-openapi-v1.0.0.yaml`, SHA-256
  `a4bfd8b09c848b398bb0f623f03a5a99b5d3abc5277af842cee111e7d42cfabe`; identical to `main` at
  commit `45175a1` on 2026-11-25). Use the upstream wiki (API Documentation, API Throttling and
  Rate Limits) as the companion reference for problem types and client retry guidance.
- **Rationale**: Constitution Principle I requires a pinned, deliberately-updated snapshot. The
  `v1.0.0` tag is the first release and matches the spec's target.
- **Alternatives considered**: Tracking `main` (non-reproducible tests); fetching the contract
  at test time (network-dependent CI).
- **Known contract/wiki differences** (OpenAPI wins; SDK handles both):
  - The OpenAPI `Problem` examples show `type: rate-limited`, while the live service and wiki
    send a URI (`https://nazrulworld.github.io/fhir-validation-service/problems/rate-limited`).
    The SDK derives the short name from the last path segment, so it accepts both.
  - The wiki lists `unsupported-fhir-version`, `package-source-not-allowed`, `package-unsafe`,
    `payload-too-large`, `method-not-allowed`, `not-found` and `internal-error`, which the
    OpenAPI only implies through generic `Problem` responses. All are in the SDK catalogue.

## R2. Python versions and platforms

- **Decision**: `requires-python = ">=3.11"`. CI matrix: CPython 3.11, 3.12, 3.13, 3.14, 3.15 on
  ubuntu-latest, macos-latest and windows-latest. Classifiers list each version, plus
  `Typing :: Typed`.
- **Rationale**: User constraint (minimum 3.11). 3.15 is the newest stable release (3.15.2).
  3.11 reaches end of life on 2027-10-31; dropping it then is a MINOR release decision, tracked
  in the changelog.
- **Alternatives considered**: Including PyPy (deferred: no user demand; pure-Python code should
  work and can be added later).

## R3. Runtime dependencies

- **Decision**: Exactly two runtime dependencies:
  - `httpx>=0.27,<1` (latest 0.28.1): the mandated transport.
  - `anyio>=4.0` (latest 4.16.0): structured concurrency for async `validate_many`. httpx
    already installs it, so it costs nothing, but it is declared explicitly because the SDK
    imports it directly (importing an undeclared transitive dependency is fragile).
- **Rationale for the `httpx<1` cap**: Constitution VI forbids *needless* upper caps. httpx 1.0
  is a planned release with announced breaking API changes, so the cap protects users from a
  known incompatibility. It is lifted after a CI job against the 1.0 pre-releases passes. A
  scheduled CI job tests the newest httpx to catch this early.
- **Alternatives considered**: `tenacity` for retries (rejected: about 60 lines of retry logic
  don't justify a dependency); `pydantic` or `msgspec` for models (rejected in clarification Q4);
  `typing_extensions` (not needed with 3.11 or newer).

## R4. Packaging, build backend and versioning

- **Decision**: PEP 621 `pyproject.toml`, `src/` layout, build backend `hatchling` (1.33) with
  `hatch-vcs` (0.5) to derive the version from git tags (`v0.1.0` → `0.1.0`). The version is
  exposed as `fvs_client.__version__` through a generated `_version.py`. Licence metadata uses
  PEP 639: `license = "Apache-2.0"`, `license-files = ["LICENSE", "NOTICE"]`.
- **Rationale**: Hatchling is a mature, widely used PEP 517 backend with PEP 639 support. A
  tag-derived version gives one source of truth, matching the constitution's rule that releases
  are cut only from tags.
- **Alternatives considered**: `uv_build` (fast and simple, but no VCS-derived versions);
  `setuptools` with `setuptools-scm` (heavier configuration); `flit` and `pdm-backend`
  (fine, but fewer plugins).

## R5. Developer tooling

- **Decision**:
  - `uv` (0.13) for environments, a committed `uv.lock`, and PEP 735 `[dependency-groups]`
    (`dev`, `test`, `docs`)
  - `ruff` (0.17) for lint and format, with a broad rule set: E, F, W, I, UP, B, SIM, RUF, S,
    D (Google docstrings), ANN, PT, ASYNC, TRY, PL
  - `mypy --strict` (2.4) and `pyright` strict (1.1.414)
  - `pre-commit` mirroring the CI checks
- **Rationale**: Constitution "Technology & Packaging Standards".
- **Alternatives considered**: Poetry or PDM (fewer standards-only choices than uv plus
  hatchling); black plus isort plus flake8 (ruff replaces all three).

## R6. Sync/async parity architecture

- **Decision**: A "sans-I/O" core. Pure functions in private modules build each request
  (`_requests.py` → `RequestSpec`: method, path, params, headers, body or stream) and parse each
  response (`_parsing.py` / `_errors.py`: status, headers and bytes → result or error). Thin
  `Client` and `AsyncClient` classes send the request, run the shared retry policy
  (`_retry.py`, sleeping through `time.sleep` or `anyio.sleep`), and call the shared parser. A
  parity test asserts that both clients expose the same public method names, parameters,
  defaults and return annotations (apart from `Awaitable`).
- **Rationale**: Constitution IV requires shared logic in one place. With the sans-I/O core,
  about 90% of the code is unit-testable without any transport.
- **Alternatives considered**: `unasync` code generation (adds a build step and generated
  files to review); having the sync client wrap the async one with `anyio.run` (fails inside an
  already running event loop, and slower).

## R7. Result models (clarification Q4)

- **Decision**: `@dataclass(frozen=True, slots=True, kw_only=True)` classes in
  `fvs_client.models`. Each parsed result has a `raw: Mapping[str, Any] | str` field (original
  body), and each top-level result has `meta: ResponseMeta`. A shared `to_dict()` mixin uses
  `dataclasses.asdict`, converting enums to their values. Closed value sets are `StrEnum`s
  (`FhirVersion`, `Severity`, `TerminologyMode`, `TxSource`, `HealthStatus`). A value the
  service sends that the enum doesn't know is kept as a plain `str` (fields are typed
  `Severity | str`), so an unknown value never fails parsing and is never lost.
- **Rationale**: Clarification Q4 (no extra dependency), FR-023, FR-029 and FR-030.
  Immutability makes results safe to share across threads and tasks.
- **Alternatives considered**: `TypedDict` (no methods, no immutability); `attrs` (extra
  dependency); `NamedTuple` (positional, awkward to evolve).

## R8. Raw results (clarification Q4 + FR-031)

- **Decision**: Every operation takes a keyword-only `raw: bool = False`. `typing.overload` on
  `Literal[True]` and `Literal[False]` gives precise return types (`RawResponse` versus the
  parsed model). `RawResponse` is a frozen dataclass with `status_code`, `headers` (an immutable
  case-insensitive mapping), `content: bytes`, the `.text` and `.json()` helpers, and `meta`.
  Error statuses still raise typed errors, whose `.response` is a `RawResponse`.
- **Rationale**: A per-call flag is the most discoverable form, and the overloads keep strict
  type checkers accurate.
- **Alternatives considered**: A `client.with_raw_response.<op>()` namespace (doubles the public
  surface); returning the `httpx.Response` (leaks the transport type into the public API and
  ties SDK semver to httpx).

## R9. Error model

- **Decision**: All errors inherit from `FVSError(Exception)`:
  - `FVSError`
    - `InputError` (+ `ValueError`): local checks before sending
    - `TransportError`
      - `FVSConnectionError`
      - `FVSTimeoutError`
    - `APIError`: a service-reported problem
      - `BadRequestError` (400/405/406/413/415/422/424)
        - `UnknownProfileError` (adds `unresolved_profiles`)
        - `DependencyConflictError` (adds `conflicts`)
        - `InvalidResourceError` (adds `issues`)
      - `AuthenticationError` (401)
      - `PermissionDeniedError` (403)
      - `NotFoundError` (404)
      - `ConflictError` (409)
      - `RateLimitError` (429; adds `scope`, `limit`, `retry_after`)
      - `ServiceUnavailableError` (503; adds `retry_after`)
      - `ServerError` (500 and any other 5xx)

  `APIError` carries `status_code`, `problem: Problem | None`, `problem_type: ProblemType | str
  | None`, `request_id` and `response: RawResponse`. A body that is not problem JSON gives
  `problem=None` and an error picked by status alone. Error messages are built from
  `title`/`detail` and `correlationId` only.
- **Rationale**: FR-020, FR-021 and FR-021a. Names avoid clashing with the builtins
  `ConnectionError` and `TimeoutError`.
- **Alternatives considered**: One class per problem type, 27 in all (too fine-grained to catch
  usefully; branching on `problem_type` covers that need).

## R10. Retry policy

- **Decision**: An internal `RetryPolicy(max_retries, backoff_base=0.5 s, backoff_max=8 s,
  max_retry_after=60 s)`:
  - Retry is triggered by 429, 503, and connection errors (`httpx.ConnectError`, not read or
    write timeouts) for safe operations.
  - The wait is `Retry-After` (whole seconds) when present, capped at `max_retry_after`; if the
    advised wait is over the cap, the SDK raises instead of sleeping. Otherwise the wait is
    full-jitter exponential backoff.
  - Defaults: validation and health `max_retries=2`; admin operations `max_retries=0`. When
    admin retry is turned on, it covers 429 and 503 only.
  - Configured per client (`retries=`); an admin override is available per call.
- **Rationale**: FR-022 and the wiki's client guidance (don't retry before `Retry-After`; on a
  multi-instance deployment a 429 may come with a short 2 s wait).
- **Alternatives considered**: Retrying on timeouts (rejected: a timed-out validation may
  still be running server-side, so retrying adds load).

## R11. Timeouts, headers, identity and secrets

- **Decision**:
  - Default `httpx.Timeout(60.0, connect=10.0)`, overridable per client and per call.
  - The user agent is `fvs-client/<ver> httpx/<ver> python/<ver>` plus an optional suffix.
  - The API key is held in a private `_SecretStr`, whose `__repr__`/`__str__` return
    `'**********'`, and is injected as `Authorization: Bearer …` only when a request is built.
    Before logging or attaching a request to an error, the SDK redacts the `Authorization`
    header.
  - `FVS_BASE_URL` / `FVS_API_KEY` are read when the arguments are omitted. Base URL missing
    in both places → `InputError`.
  - TLS verification stays on (httpx default). `verify`, `proxy` and other options go through a
    caller-supplied `httpx.Client` or `httpx.AsyncClient`, which the SDK does not close.
- **Rationale**: FR-001 to FR-005 and Constitution V.

## R12. Resource input and content negotiation

- **Decision**:
  - `dict` → JSON-encode → `application/fhir+json`.
  - `str`/`bytes` → sniff the first non-whitespace byte (`<` → `application/fhir+xml`, `{` →
    `application/fhir+json`, anything else → `InputError`).
  - `os.PathLike` → open and stream the file; the suffix (`.json`/`.xml`) decides the content
    type, falling back to sniffing.
  - An explicit `content_type=` overrides all of the above.
  - Result format: `ResultFormat.SUMMARY` (default, `Accept: application/json`) →
    `ValidationResult`; `OPERATION_OUTCOME_JSON` (`application/fhir+json`) →
    `OperationOutcomeResult` with a `dict` body; `OPERATION_OUTCOME_XML`
    (`application/fhir+xml`) → `OperationOutcomeResult` with a `str` body.
- **Rationale**: FR-006 and FR-010. A file is streamed, not read into memory.

## R13. Query encoding

- **Decision**: Rely on httpx query encoding. Verified with httpx 0.28.1: `ig=a.b#1.0|c#2` is
  sent as `a.b%231.0%7Cc%232`; profiles are joined with `,` (sent as `%2C`, which the server
  decodes before splitting; covered by the integration test). Path segments (`/igs/{name}/
  {version}`) are encoded with `urllib.parse.quote(segment, safe="")`.
- **Rationale**: Spec edge case: a raw `#` would silently drop the IG version.

## R14. Concurrency helper (`validate_many`)

- **Decision**: Async: `anyio` task group plus `CapacityLimiter(concurrency)` (default 8).
  Sync: `concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)` sharing the one
  `httpx.Client`, which is thread-safe. Both return `list[ValidationResult |
  OperationOutcomeResult | FVSError]` in input order; `InputError` per item is captured, not
  raised.
- **Rationale**: FR-012 and SC-005. One failure never cancels the others.

## R15. Testing strategy

- **Decision**:
  - `pytest` 9 with anyio's pytest plugin. Async tests run on the asyncio backend, plus trio
    in a single CI job.
  - **Unit tests**: `httpx.MockTransport` (no extra dependency) plus JSON fixtures copied from
    the contract and wiki examples.
  - **Contract tests**: `openapi-core` (test-only) checks every SDK-built request and every
    fixture response against the pinned OpenAPI.
  - **Integration tests**: run when `FVS_IT_BASE_URL` is set; CI starts
    `ghcr.io/nazrulworld/fhir-validation-service:1.0.0` with `postgres:16.8-alpine` using
    Docker Compose on ubuntu.
  - `coverage` via `pytest-cov`, branch coverage, `fail_under = 90`.
  - Small `hypothesis` property tests for input sniffing and problem-type parsing.
- **Rationale**: Constitution III.
- **Alternatives considered**: `respx` (good, but unnecessary given MockTransport);
  `testcontainers` (Compose matches upstream's own documented setup).

## R16. Documentation

- **Decision**: MkDocs with the Material theme (9.8) and `mkdocstrings[python]` (1.0), with
  Google-style docstrings, published to GitHub Pages from CI. Pages: Installation, Quick start,
  Validation, IG packages & validator contexts, Health, Errors & retries, Async & batch, Raw
  responses, API reference, Changelog.
- **Rationale**: FR-027. These are the de facto tools for Python library docs and can render
  the API reference from docstrings.
- **Alternatives considered**: Sphinx with furo (more configuration); Zensical (0.1.3; too
  young; revisit later).

## R17. CI/CD and release

- **Decision**: GitHub Actions:
  - `ci.yml`, on push and PR: ruff, mypy, pyright, the test matrix, coverage, `uv build`,
    `twine check --strict`, and an install smoke test of the wheel in a clean virtual
    environment.
  - `integration.yml`: Compose-based tests, on PR and nightly.
  - `release.yml`, on `v*` tags:
    - build once, upload the artifacts
    - publish to TestPyPI
    - smoke-install
    - publish to PyPI with `pypa/gh-action-pypi-publish` (Trusted Publishing, OIDC, with
      digital attestations)
    - create a GitHub release with notes taken from `CHANGELOG.md`
  - `docs.yml`: deploy to Pages.
  - Dependabot for GitHub Actions and uv.
  - `pip-audit` against the exported lock.
- **Rationale**: Constitution V and quality gates; SC-008.

## R18. Logging

- **Decision**: `logging.getLogger("fvs_client")` with a `NullHandler`. Each attempt logs at
  DEBUG (method, path, status, elapsed ms, request id, attempt number); each retry decision
  logs at INFO. Bodies, query values for `tx`, and headers are never logged.
- **Rationale**: FR-028 and Constitution V.
