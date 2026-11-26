---

description: "Task list for the fvs_client Python SDK (feature 001-fvs-python-sdk)"
---

# Tasks: FHIR Validation Service Python SDK (`fvs_client`)

**Input**: Design documents from `specs/001-fvs-python-sdk/`

**Prerequisites**: [plan.md](./plan.md), [spec.md](./spec.md), [research.md](./research.md), [data-model.md](./data-model.md), [contracts/public-api.md](./contracts/public-api.md), [contracts/http-mapping.md](./contracts/http-mapping.md), [contracts/fvs-openapi-v1.0.0.yaml](./contracts/fvs-openapi-v1.0.0.yaml), [quickstart.md](./quickstart.md)

**Tests**: REQUIRED. Constitution Principle III (Test-First, NON-NEGOTIABLE) applies: in every phase, write the test tasks first and confirm they FAIL before starting the implementation tasks.

**Organization**: Tasks are grouped by user story (US1–US6 as numbered in spec.md). Phases follow priority order: US1, US2 and US6 (P1), then US3 and US4 (P2), then US5 (P3).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on an unfinished task)
- **[Story]**: The user story the task belongs to (US1–US6)
- Paths are relative to the repository root (single-project `src/` layout, see plan.md)

## Conventions every task MUST follow

- Public models: `@dataclass(frozen=True, slots=True, kw_only=True)` with `to_dict()`, a `raw` field and, on top-level results, `meta: ResponseMeta` (data-model.md).
- Enum-typed fields are declared as `Enum | str`. A value the service sends that the enum does not know is kept as a `str` and never raises (research R7).
- Every public symbol has a Google-style docstring. Any module not re-exported from `fvs_client` is `_`-prefixed.
- No code path may log or include in a `repr`/`str` the API key, resource bodies, request/response headers, or the `tx` query value (Constitution V, FR-003, FR-028).
- Scenario tests use `httpx.MockTransport` and the fixtures in `tests/fixtures/`. No real network is used outside `tests/integration/`.
- Tests that sleep use an injectable fake sleep and clock (no real waiting).

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Repository, packaging skeleton and tooling, so `uv sync`, `uv run pytest` and the linters run (on empty code).

- [X] T001 Initialise the git repository (default branch `main`) and add a `.gitignore` covering Python, uv, coverage, mkdocs `site/`, `.idea/`, `.env` and `src/fvs_client/_version.py`, at `.gitignore`
- [X] T002 Create `pyproject.toml` with:
  - PEP 621 metadata: `name = "fvs_client"`, `requires-python = ">=3.11"`, `license = "Apache-2.0"`, `license-files = ["LICENSE", "NOTICE"]`, `readme = "README.md"`, `dynamic = ["version"]`
  - runtime dependencies exactly `httpx>=0.27,<1` and `anyio>=4.0`
  - classifiers for Python 3.11, 3.12, 3.13, 3.14 and 3.15, `Typing :: Typed`, and `License :: OSI Approved :: Apache Software License`
  - `[build-system]` using `hatchling` + `hatch-vcs`, with `[tool.hatch.version] source = "vcs"`, `fallback-version = "0.0.0"`, and the build hook writing `src/fvs_client/_version.py`
  - PEP 735 `[dependency-groups]`:
    - `test`: pytest, pytest-cov, anyio[trio], openapi-core, hypothesis, pyyaml
    - `lint`: ruff, mypy, pyright, pre-commit, pip-audit, twine
    - `docs`: mkdocs-material, mkdocstrings[python]
    - `dev`: includes the three groups above
- [X] T003 Add tool configuration to `pyproject.toml`:
  - `[tool.ruff]`: target py311, line-length 100, rule sets E, F, W, I, UP, B, SIM, RUF, S, D (google convention), ANN, PT, ASYNC, TRY, PL; tests may relax S101/D/ANN
  - `[tool.mypy] strict = true`, `python_version = "3.11"`
  - `[tool.pyright] typeCheckingMode = "strict"`, `pythonVersion = "3.11"`
  - `[tool.pytest.ini_options]`: markers `integration` and `perf`; `addopts = "-m 'not integration and not perf'"`; `filterwarnings = ["error"]`
  - `[tool.coverage]`: `branch = true`, `fail_under = 90`, `source = ["fvs_client"]`
- [X] T004 [P] Add the Apache License 2.0 full text in `LICENSE` and a `NOTICE` file naming the project and copyright holder
- [X] T005 [P] Create the package skeleton:
  - `src/fvs_client/__init__.py`: module docstring; empty `__all__`; `__version__` imported from `fvs_client._version`, with fallback `"0.0.0"` when that module is missing
  - empty `src/fvs_client/py.typed`
  - empty package files `src/fvs_client/_sync/__init__.py` and `src/fvs_client/_async/__init__.py`
- [X] T006 [P] Create test directories, each with an `__init__.py`: `tests/unit/`, `tests/contract/`, `tests/parity/`, `tests/scenarios/`, `tests/integration/`, `tests/typing/`, `tests/perf/`, `tests/fixtures/`. Then create `tests/conftest.py` with an `anyio_backend` fixture returning `"asyncio"` (the CI trio job overrides it through the `FVS_TEST_ANYIO_BACKEND` env var). In `tests/conftest.py`, also add:
  - a `mock_router` fixture that registers canned responses per `(method, path)` and builds an `httpx.MockTransport`
  - a `client` fixture yielding `Client(base_url="https://fvs.test", api_key="test-key", http_client=httpx.Client(transport=…))`. It imports `fvs_client` inside the fixture function, not at the top of `conftest.py`, so `conftest.py` still loads before `Client` exists (T029–T030) and T013's pytest run passes

  It is sync-only for now; T061 parametrises it over both clients
- [X] T007 [P] Copy `specs/001-fvs-python-sdk/contracts/fvs-openapi-v1.0.0.yaml` unchanged into `tests/contract/fvs-openapi-v1.0.0.yaml`, and add `tests/contract/test_snapshot_pin.py`, which asserts its SHA-256 equals `a4bfd8b09c848b398bb0f623f03a5a99b5d3abc5277af842cee111e7d42cfabe`
- [X] T008 [P] Create `.pre-commit-config.yaml` with hooks for ruff (check + format), mypy (strict, with httpx and anyio as additional dependencies), end-of-file-fixer, trailing-whitespace and check-yaml
- [X] T009 [P] Create stubs for `README.md` (title, one-line description, install command `pip install fvs_client`, licence badge), `CHANGELOG.md` (Keep a Changelog header with an `## [Unreleased]` section), `CONTRIBUTING.md` (uv workflow, test-first rule, Conventional Commits) and `SECURITY.md` (private vulnerability reporting through GitHub Security Advisories)
- [X] T010 [P] Create `.github/workflows/ci.yml`, triggered on push to `main`, on pull requests, and by `workflow_call` (so `release.yml` can reuse it):
  - `lint` job: ruff check, `ruff format --check`, `mypy --strict src tests`, `pyright`
  - `test` job: matrix of Python 3.11, 3.12, 3.13, 3.14 and 3.15 × ubuntu-latest, macos-latest and windows-latest; runs `uv run pytest --cov --cov-branch --cov-fail-under=90`
  - `trio` job: one Python version with `FVS_TEST_ANYIO_BACKEND=trio`
  - `build` job: `uv build`, `twine check --strict dist/*`, then install the wheel into a clean venv and run `python -c "import fvs_client"`
  - `audit` job: `uv export --no-hashes | pip-audit -r /dev/stdin`
- [X] T011 [P] Create `.github/dependabot.yml` with weekly updates for the `github-actions` and `uv` ecosystems
- [X] T012 [P] Create `.github/workflows/integration.yml`, triggered on pull requests, nightly, and by `workflow_call` (so `release.yml` can reuse it):
  - checks out `nazrulworld/fhir-validation-service` at tag `v1.0.0`
  - writes `.env` from repository secrets or generated random keys (`PG_PASSWORD`, `FV_PG_PASSWORD`, `FV_ADMIN_API_KEY`, `FV_VALIDATOR_API_KEY`)
  - runs `FV_TAG=1.0.0 docker compose up -d --wait`
  - runs `uv run pytest -m integration` with `FVS_IT_BASE_URL=http://127.0.0.1:8880`, `FVS_IT_API_KEY` and `FVS_IT_ADMIN_API_KEY`
  - always runs `docker compose down -v` at the end
- [X] T013 Run `uv lock` to create `uv.lock`, and verify that `uv sync --all-groups && uv run pytest` succeeds; it collects only `tests/contract/test_snapshot_pin.py` (depends on T002–T007)

**Checkpoint**: The toolchain runs green on an empty package.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The sans-I/O core that every story uses: configuration and secrets, shared models, the full error hierarchy with problem parsing, the request and response plumbing, logging, and the sync transport and client shell.

**⚠️ CRITICAL**: No user-story work can begin until this phase is complete.

### Tests for Foundational (write first, confirm FAIL)

- [X] T014 [P] Create the shared fixtures in `tests/fixtures/`, using the examples from `contracts/fvs-openapi-v1.0.0.yaml` and the upstream wiki API Documentation:
  - `validation/patient_invalid.json` (the 4-message wiki example: 3 ERROR + 1 WARNING, `fhirVersion` "R4", `igPackage` null, `igOwner` "system", `igShareable` true)
  - `validation/patient_valid.json`
  - `validation/operation_outcome.json`
  - `validation/operation_outcome.xml`
  - `problems/<short-name>.json`: one per problem type, all 27 in FR-021a, each with `type` set to the full URI `https://nazrulworld.github.io/fhir-validation-service/problems/<short-name>`, plus `title`, `status` and `correlationId`. Type-specific members: `issues` for invalid-resource, `unresolvedProfiles` for unknown-profile, `conflicts` for dependency-conflict, and `scope`, `limit`, `retryAfterSeconds` for rate-limited
  - `admin/include_single.json`, `admin/include_two.json`, `admin/exclude.json`, `admin/context_access.json`, `admin/ig_registration.json`, `admin/ig_access.json`, `admin/dependencies.json`, `admin/files.json`
  - `health/health_up.json`, `health/health_down.json`, `health/readiness_up.json`, `health/readiness_down.json`, `health/liveness.json`
  - `tests/fixtures/__init__.py` with a `load(path) -> bytes` helper
- [X] T015 [P] Write `tests/unit/test_config.py` covering:
  - `base_url` / `api_key` resolution from arguments, then from the `FVS_BASE_URL` / `FVS_API_KEY` env vars
  - a base URL missing from both → `InputError`
  - trailing-slash normalisation
  - `_SecretStr` `repr`/`str` is `'**********'`
  - `repr(Client(...))` never contains the key
  - `headers={"Authorization": ...}` → `InputError`
  - the default timeout is `httpx.Timeout(60.0, connect=10.0)`
  - `Client(timeout=None)` and a `timeout` given as an `httpx.Timeout` with any `None` field → `InputError` (Constitution IV: no unbounded waits); a per-call `timeout=None` uses the client default
  - `extra_headers={"authorization": ...}` on any call → `InputError`
  - the `User-Agent` format is `fvs-client/<v> httpx/<v> python/<v>[ <suffix>]`
  - `RetryConfig` defaults are `max_retries=2, admin_max_retries=0, backoff_base=0.5, backoff_max=8.0, max_retry_after=60.0`
- [X] T016 [P] Write `tests/unit/test_models_common.py` covering:
  - `FhirVersion.parse` accepts "stu3", "r4", "R4B" and "r5" in any case, and raises `InputError` for "R6"/"DSTU2"
  - `RateLimitInfo` is parsed from the `RateLimit-Limit`, `RateLimit-Remaining`, `RateLimit-Reset` and `Retry-After` headers (all `None` when the headers are absent)
  - `ResponseMeta` fields `status_code`, `request_id` (`X-Request-Id`), `rate_limit`, `elapsed_seconds` and `attempts`
  - `RawResponse` exposes `status_code`, case-insensitive read-only `headers`, `content`, `.text`, `.json()` and `meta`
  - `to_dict()` converts enums to their values
  - an unknown enum value stays a `str`
- [X] T017 [P] Write `tests/unit/test_problems.py`:
  - parse every `tests/fixtures/problems/*.json`
  - the `type_uri` is kept, and `type` is the short name taken from the last non-empty path segment; a bare `type` without `/` is used as-is
  - `ProblemType.from_uri` matches on the short name for any host and returns `None` for unknown names
  - unknown members go into `extensions`
  - the status→class mapping table from `contracts/http-mapping.md#error-mapping` is parametrised over every row, including any other 4xx → `APIError` and any other 5xx → `ServerError`
  - a non-problem body (for example a 502 `text/html` page) → `problem=None`, the class is picked by status, and the raw text is kept on `.response`
  - `str(error)` has the format `"<status> <short name>: <detail or title> (request id <id>)"`
- [X] T018 [P] Write `tests/unit/test_logging.py`:
  - the `fvs_client` logger has a `NullHandler`
  - the per-attempt DEBUG record contains the method, path, status, elapsed ms and request id
  - captured log text never contains the API key, the `Authorization` header, the request body, or the `tx` value (use caplog with a client sending through `MockTransport`)
- [X] T019 [P] Write `tests/unit/test_transport_sync.py` using `MockTransport`:
  - the `Authorization: Bearer <key>` header is sent only when a key is configured
  - `User-Agent` and `Accept` are set
  - `httpx.ConnectError` → `FVSConnectionError`
  - `httpx.TimeoutException` → `FVSTimeoutError`, and the original exception is chained
  - a caller-supplied `http_client` is used and is NOT closed by `Client.close()`
  - an owned client IS closed
  - the `with Client(...)` block closes the owned client
- [X] T020 [P] Write `tests/integration/conftest.py`, which skips unless `FVS_IT_BASE_URL` is set and provides `it_client` (`FVS_IT_API_KEY`) and `it_admin_client` (`FVS_IT_ADMIN_API_KEY`) fixtures marked `integration`

### Implementation for Foundational

- [X] T021 [P] Implement the shared models in `src/fvs_client/models.py`:
  - a `_ToDictMixin` providing `to_dict()`
  - `StrEnum`s `FhirVersion` (with a `parse` classmethod), `HealthStatus`, `RateLimitScope` and `ProblemType`; `ProblemType` has all 27 short names from FR-021a and a `from_uri` classmethod
  - dataclasses `RateLimitInfo`, `ResponseMeta`, `RawResponse` and `Problem`
  - `Problem` fields: `type_uri`, `type`, `title`, `status`, `detail`, `correlation_id`, `issues`, `unresolved_profiles`, `conflicts`, `scope`, `limit`, `retry_after_seconds`, `extensions`
- [X] T022 [P] Implement the full error hierarchy in `src/fvs_client/errors.py`, exactly as in `contracts/public-api.md#errors`:
  - `FVSError`
  - `InputError(FVSError, ValueError)`
  - `TransportError`, `FVSConnectionError`, `FVSTimeoutError`
  - `APIError`, with `status_code`, `problem`, `problem_type`, `request_id` and `response`
  - the subclasses:
    - `BadRequestError`
    - `InvalidResourceError(.issues)`
    - `UnknownProfileError(.unresolved_profiles)`
    - `DependencyConflictError(.conflicts)`
    - `AuthenticationError`
    - `PermissionDeniedError`
    - `NotFoundError`
    - `ConflictError`
    - `RateLimitError(.scope, .limit, .retry_after)`
    - `ServiceUnavailableError(.retry_after)`
    - `ServerError`
  - the `__str__` format from T017
- [X] T023 Implement `src/fvs_client/_problems.py`:
  - `parse_problem(headers, content) -> Problem | None`, which accepts `application/problem+json`, or any JSON with `type` and `status` members
  - `short_name(type_uri)`
  - `error_for(raw: RawResponse) -> APIError`, which applies the status table and refines 400 by short name: `invalid-resource` → `InvalidResourceError`, `unknown-profile` → `UnknownProfileError`, `dependency-conflict` → `DependencyConflictError` (depends on T021, T022)
- [X] T024 [P] Implement `src/fvs_client/_config.py`:
  - `_SecretStr`
  - `resolve_settings(base_url, api_key, timeout, headers, user_agent_suffix)`, reading the env vars `FVS_BASE_URL` and `FVS_API_KEY`
  - the constant `DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)`
  - `RetryConfig`, a frozen dataclass with the defaults from T015
  - `build_user_agent(suffix)`
- [X] T025 [P] Implement `src/fvs_client/_logging.py`:
  - `logger = logging.getLogger("fvs_client")` with `NullHandler`
  - `log_attempt(method, path, status, elapsed, request_id, attempt)` at DEBUG
  - `log_retry(...)` at INFO
  - `redact_headers()`, which replaces the `Authorization` value with `'**********'`
- [X] T026 Implement the request plumbing in `src/fvs_client/_requests.py`:
  - `RequestSpec`, a frozen dataclass: `method`, `path`, `params`, `headers`, `content | json | files | stream`, `accept`, `is_admin: bool`
  - `quote_segment(s)` using `urllib.parse.quote(s, safe="")`
  - `join_url(base_url, path)`, with no duplicate slashes
  - `default_headers(settings, accept)`, which injects `Authorization: Bearer` only when a key is set (depends on T024)
- [X] T027 Implement the response plumbing in `src/fvs_client/_parsing.py`:
  - `build_meta(status, headers, elapsed, attempts) -> ResponseMeta`
  - `build_raw(status, headers, content, meta) -> RawResponse`
  - `decode_json(raw)`
  - `finalize(raw, parser, *, want_raw)`: returns `raw` when `want_raw`; calls `parser(raw)` on 2xx; otherwise raises `_problems.error_for(raw)` (depends on T021, T023)
- [X] T028 Implement the sync send loop in `src/fvs_client/_sync/transport.py`:
  - `SyncTransport(http_client, settings, sleep=time.sleep, clock=time.perf_counter)`
  - `send(spec, *, timeout, extra_headers) -> RawResponse`: builds the `httpx.Request`, measures elapsed time, maps httpx exceptions to `FVSConnectionError`/`FVSTimeoutError` with `raise … from exc`, and calls `_logging.log_attempt`
  - retries are added in US2 (T049) (depends on T025–T027)
- [X] T029 Implement the `Client` shell in `src/fvs_client/_sync/client.py`:
  - `__init__(base_url=None, *, api_key=None, timeout=DEFAULT_TIMEOUT, retries=None, headers=None, user_agent_suffix=None, http_client=None)`
  - an owned or caller-supplied `httpx.Client`
  - `close()`, `__enter__`, `__exit__`
  - `__repr__` showing the base URL and a masked key
  - a private `_request(spec, parser, *, raw, timeout, extra_headers)` helper (depends on T024, T028)
- [X] T030 Export the foundation from `src/fvs_client/__init__.py`: `Client`, `RetryConfig`, `FhirVersion`, `HealthStatus`, `RateLimitScope`, `ProblemType`, `ResponseMeta`, `RateLimitInfo`, `RawResponse`, `Problem`, every error class, `__version__` and `SUPPORTED_API = "1.0"`. Then run T015–T019 and confirm they pass

**Checkpoint**: The foundation is ready. `uv run pytest tests/unit` passes, and mypy and pyright strict are clean.

---

## Phase 3: User Story 1 - Validate a FHIR resource (Priority: P1) 🎯 MVP

**Goal**: `Client.validate(...)` validates a resource given as a dict, JSON str/bytes, XML str/bytes or a file path:
- against any FHIR version, an optional IG (single or two-IG), profiles, `tx` and `txMode`
- returns a `ValidationResult` (default), an `OperationOutcomeResult` (JSON/XML) or a `RawResponse` (`raw=True`)

**Independent Test**: Run `tests/scenarios/test_us1_validate.py` (MockTransport) and `tests/integration/test_us1_validate.py` (quickstart §4). A valid R4 Patient → `valid=True`, `context.key == "base"`. An invalid one → `valid=False` with the issues listed and no exception. The IG `#` and `|` are encoded; OperationOutcome formats and `raw` work.

### Tests for User Story 1 (write first, confirm FAIL)

- [X] T031 [P] [US1] Write `tests/unit/test_inputs.py`:
  - a `dict` → JSON body with `Content-Type: application/fhir+json`
  - `str`/`bytes` whose first non-whitespace char is `{` → `application/fhir+json`; `<` → `application/fhir+xml`; anything else → `InputError`
  - an `os.PathLike` is streamed, not read whole (the test asserts the body is an iterator/file); the suffix `.json`/`.xml` decides the type, and other suffixes fall back to sniffing
  - an explicit `content_type=` overrides everything
  - a Hypothesis property test: random leading whitespace never changes the sniffed type
- [X] T032 [P] [US1] Write `tests/unit/test_validation_options.py`, quoting the data-model.md rules:
  - `IgRef`: "`name` non-empty; no `#`, `|`, `/` or whitespace"; "`version` `None` / `"latest"` / exact version"; `IgRef.parse("name#1.0.0")` and `str()` round-trip
  - `ig`: "Rendered string ≤ 256 chars; a two-IG form needs exact versions in both parts; version series (`1.2.x`) rejected"
  - `profiles`: "≤ 10 distinct after trim/dedupe (order preserved); each ≤ 1024 chars; no empty items"
  - `tx`: "≤ 512 chars; `http`/`https` scheme; no query, fragment or user info"
  - `tx_mode`: "one of the 3 values; `tx` together with `none` is rejected"
  - `TerminologySettings`: "`server` required when `mode=server`; forbidden when `mode=none`; ≤ 512 chars"
  - passing both `options=` and keyword options → `InputError`
- [X] T033 [P] [US1] Write `tests/unit/test_requests_validate.py`:
  - `build_validate` produces `POST /R4/validate` (the version is upper-cased)
  - `ig="a.b#1.0|c#2"` is encoded in the URL as `ig=a.b%231.0%7Cc%232`
  - profiles are comma-joined into a single `profile` param
  - `tx` and `txMode` params appear only when set
  - `Accept` is `application/json` for SUMMARY, `application/fhir+json` for OPERATION_OUTCOME_JSON and `application/fhir+xml` for OPERATION_OUTCOME_XML
  - `is_admin=False`
- [X] T034 [P] [US1] Write `tests/unit/test_parsing_validation.py`:
  - `parse_validation` on `tests/fixtures/validation/patient_invalid.json`, with the headers `X-Validation-Context: base`, `X-Validation-Context-Owner: system`, `X-Validation-Context-Shareable: true`, `X-Tx-Mode: none`, `X-Tx-Source: context` and `X-Request-Id`
  - assert every `ValidationResult` field (`valid`, `issues`, `fhir_version`, `applied_profiles`, `ig_package`, `ig_owner`, `ig_shareable`, `context`, `meta`, `raw`)
  - the helpers: `errors` (FATAL+ERROR), `warnings`, `information`, `has_errors`, `issues_by_severity(...)`, and `context.is_base`
  - an unknown top-level field is kept in `raw` and does not fail
  - `OperationOutcomeResult` from JSON → `body` is a dict and `has_errors` works; from XML → `body` is a str and `has_errors` raises `NotImplementedError`
- [X] T035 [P] [US1] Write `tests/contract/test_validate_contract.py`, using `openapi-core` against `tests/contract/fvs-openapi-v1.0.0.yaml`:
  - every request built by `build_validate` (dict, XML, ig, profiles, tx/txMode, each result format) is valid for operation `validationApiValidate`
  - the fixture responses (200 JSON and OperationOutcome; 400/401/403/404/424/429/503 problems) validate against the declared responses
- [X] T036 [P] [US1] Write `tests/scenarios/test_us1_validate.py`, implementing spec US1 acceptance scenarios 1–7 against `Client` with `MockTransport`:
  1. a valid Patient with no IG
  2. an invalid resource → result, no exception
  3. the IG forms `name#version`, `name#latest` and bare `name`, with the concrete version reported
  4. OperationOutcome JSON and XML
  5. `raw=True` returns a `RawResponse`, and a parsed result keeps `raw` and supports `to_dict()`
  6. profiles + tx/txMode are sent, and the terminology headers are reported
  7. an XML resource
  The tests are written as functions over a `client` fixture, so US3 can parametrise them over `AsyncClient`
- [X] T037 [P] [US1] Write `tests/integration/test_us1_validate.py` (uses the `it_client` fixture from T020), implementing quickstart §4 against the live service: a valid Patient → `valid` True with the dom-6 WARNING; the invalid Patient → ≥ 2 errors; OperationOutcome JSON; `raw=True`; an XML resource
- [X] T038 [P] [US1] Write `tests/typing/test_validate_overloads.py`, using `typing.assert_type`:
  - `validate(..., fhir_version="R4")` → `ValidationResult`
  - `result_format=ResultFormat.OPERATION_OUTCOME_JSON` → `OperationOutcomeResult`
  - `raw=True` → `RawResponse`
  It is checked by mypy and pyright in CI

### Implementation for User Story 1

- [X] T039 [P] [US1] Add the validation models to `src/fvs_client/models.py`:
  - `StrEnum`s `Severity` (with an `is_error` property, true for FATAL/ERROR), `TerminologyMode`, `TxSource` and `ResultFormat`
  - `TerminologySettings`, with `__post_init__` enforcing "required when `mode=server`; forbidden when `mode=none`; ≤ 512 chars; http(s) base URL with no query, fragment or user info"
  - `IgRef`, with `parse` and `__str__`
  - `ValidationOptions`
  - `ValidationIssue`
  - `ValidationContextInfo`, with an `is_base` property
  - `ValidationResult`, with `errors`, `warnings`, `information`, `has_errors` and `issues_by_severity`
  - `OperationOutcomeResult`, with `has_errors`
- [X] T040 [P] [US1] Implement `src/fvs_client/_inputs.py`:
  - `prepare_resource(resource, content_type) -> (content_or_stream, content_type)`, following the T031 rules
  - `check_validation_options(...) -> ValidationOptions`, enforcing every T032 rule and raising `InputError` with a clear message that names the limit
  - `render_ig(ig) -> str`
- [X] T041 [US1] Implement `build_validate(fhir_version, resource, options) -> RequestSpec` in `src/fvs_client/_requests.py`. The params are `ig`, `profile` (comma-joined), `tx` and `txMode`; `Accept` follows `result_format`; httpx handles query encoding (research R13) (depends on T039, T040)
- [X] T042 [US1] Implement `parse_validation(raw) -> ValidationResult` and `parse_operation_outcome(raw, fmt) -> OperationOutcomeResult` in `src/fvs_client/_parsing.py`, plus `build_context_info(headers)`, which maps the six `X-Validation-Context*`/`X-Tx-*` headers per `contracts/http-mapping.md` (depends on T039)
- [X] T043 [US1] Implement `Client.validate(...)` in `src/fvs_client/_sync/client.py`:
  - the signature from `contracts/public-api.md#validation-story-1`
  - `@overload`s for `raw: Literal[True]` and for each `result_format` literal
  - `options=` and keyword options are mutually exclusive
  - the per-call `timeout` and `extra_headers`
  - the request is sent through `_request` (depends on T041, T042)
- [X] T044 [US1] Export `Severity`, `TerminologyMode`, `TxSource`, `ResultFormat`, `IgRef`, `ValidationOptions`, `TerminologySettings`, `ValidationResult`, `ValidationIssue`, `OperationOutcomeResult` and `ValidationContextInfo` from `src/fvs_client/__init__.py`; add Google-style docstrings with a usage example to `Client.validate`; then run T031–T038 and confirm they pass

**Checkpoint**: US1 is fully functional and independently testable. This is the MVP.

---

## Phase 4: User Story 2 - Handle service errors and limits predictably (Priority: P1)

**Goal**: Every documented failure surfaces as the right typed error, carrying the problem details, request id and rate-limit information. Bounded retries honour `Retry-After` for 429 and 503 (and connect errors on safe operations).

**Independent Test**: `tests/scenarios/test_us2_errors.py` turns each of the 27 problem fixtures into the right class and fields, and checks the retry behaviour with a fake sleep. `tests/integration/test_us2_errors.py` runs quickstart §5.

### Tests for User Story 2 (write first, confirm FAIL)

- [X] T045 [P] [US2] Write `tests/unit/test_retry.py`, which asserts every row of `contracts/http-mapping.md#retry-decision-table`:
  - **429**: with `Retry-After` ≤ `max_retry_after` (60 s) → wait exactly `Retry-After`; > 60 s → no retry, raise immediately
  - **503**: with `Retry-After` → wait that long; without it (for example `tx-registry-unavailable`) → full-jitter backoff within `[0, min(backoff_max=8.0, backoff_base=0.5 * 2**attempt)]`
  - **Connect error**: on a safe operation → retry; on an admin operation → never
  - **Never retried**: read/write timeouts, other statuses, other errors
  - **Attempt limits**: stop after `max_retries` (default 2) for safe operations; admin operations default to `admin_max_retries=0`, and when enabled they retry 429/503 only
  - **Overrides**: the per-call admin `retries=` override applies
- [X] T046 [P] [US2] Write `tests/scenarios/test_us2_errors.py` (functions over the `client` fixture), implementing spec US2 acceptance scenarios 1–6:
  - **Every problem fixture** (all 27 `tests/fixtures/problems/*.json`): the expected class, `status_code`, `problem_type`, `request_id` (from `X-Request-Id`) and `problem.correlation_id`
  - **Problem-specific fields**:
    - `UnknownProfileError.unresolved_profiles`
    - `InvalidResourceError.issues`
    - `DependencyConflictError.conflicts`
    - `RateLimitError.scope`, `.limit` and `.retry_after`
  - **Rate-limit headers**: `RateLimit-*` values appear in `meta.rate_limit` on success and on errors
  - **Retries**: with retry enabled, 429 then 200 results in one sleep equal to `Retry-After` and `meta.attempts == 2`; with retry disabled (`retries=0`), it raises `RateLimitError`
  - **Transport errors**: `FVSConnectionError` and `FVSTimeoutError` are distinct from `APIError`
  - **Non-problem body**: a 502 with an HTML body → `ServerError` with `problem is None`
- [X] T047 [P] [US2] Write `tests/integration/test_us2_errors.py`, implementing quickstart §5 against the live service:
  - a wrong key → `AuthenticationError` (401) with `request_id`
  - an unresolvable profile → `UnknownProfileError`
  - `ig="no.such.ig#1.0.0"` → `NotFoundError` with `problem_type == ProblemType.PACKAGE_NOT_FOUND`
  - `fhir_version="R6"` → `InputError`, with nothing sent
  - 11 profiles → `InputError`
  - `Client(base_url="http://127.0.0.1:1").validate(...)` → `FVSConnectionError`

### Implementation for User Story 2

- [X] T048 [US2] Implement `src/fvs_client/_retry.py`:
  - a pure `RetryPolicy`, built from `RetryConfig`
  - `decide(attempt, *, is_admin, raw: RawResponse | None, exc: TransportError | None, rng) -> float | None`, returning seconds to wait or `None` to stop
  - `Retry-After` is parsed as integer seconds
  - full-jitter exponential backoff
  - the `max_retry_after` cap
  - admin operations never retry after connect errors or timeouts (FR-022)
- [X] T049 [US2] Integrate retries into `SyncTransport.send` in `src/fvs_client/_sync/transport.py`:
  - loop until `decide` returns `None`, sleeping through the injected `sleep`
  - set `ResponseMeta.attempts` and `elapsed_seconds` from the final attempt
  - call `_logging.log_retry` on each retry decision
  - the per-call `retries` override applies to admin specs (depends on T048)
- [X] T050 [US2] Accept `retries: RetryConfig | int | None` in `Client.__init__` (`src/fvs_client/_sync/client.py`): an `int` sets `max_retries` for safe operations, and `None` gives the `RetryConfig()` defaults. Pass the policy to `SyncTransport` (depends on T049)
- [X] T051 [US2] Fill in `RateLimitError` and `ServiceUnavailableError` in `src/fvs_client/_problems.py`:
  - `retry_after` comes from the `Retry-After` header, falling back to `problem.retry_after_seconds`
  - `RateLimitError` gets `scope` and `limit` from the problem body
  - `meta.rate_limit` is set on every `APIError`
- [X] T052 [US2] Add the "Errors & retries" section to the `Client` class docstring in `src/fvs_client/_sync/client.py`, and docstrings for every class in `src/fvs_client/errors.py` naming their statuses and problem types. Then run T045–T047 and confirm they pass

**Checkpoint**: US1 and US2 both work on their own. Failures are fully typed, and retries are bounded.

---

## Phase 5: User Story 6 - Install and adopt the SDK easily (Priority: P1)

**Goal**: A releasable, typed, documented package: correct metadata, published by tag through Trusted Publishing, with a README quick start and a docs site.

**Independent Test**: `uv build` → `twine check --strict` → `scripts/check_dist.py` passes → install the wheel into a fresh Python 3.11 venv and run `import fvs_client`. A Python 3.10 install is refused. The typing tests pass under mypy and pyright strict (quickstart §3).

### Tests for User Story 6 (write first, confirm FAIL)

- [X] T053 [P] [US6] Write `tests/unit/test_public_api.py`:
  - `fvs_client.__all__` equals the export list in `contracts/public-api.md#top-level-exports-fvs_client__all__` (limited to symbols delivered so far; the list is extended in US3, US4 and US5)
  - every exported symbol has a non-empty docstring
  - so does every public method and property (no leading `_`) of every exported class, and of the sub-client classes reachable as `Client.contexts`/`.packages`/`.health` and their async versions
  - `__version__` is a PEP 440 string
  - `SUPPORTED_API == "1.0"`
  - no exported symbol's `__module__` starts with a `_`-prefixed private module, except for re-exported clients
- [X] T054 [P] [US6] Write `scripts/check_dist.py`, which takes the `dist/` path and opens the built wheel and sdist. It asserts:
  - `py.typed`, `LICENSE` and `NOTICE` are present
  - the metadata has `Requires-Python: >=3.11` and `License-Expression: Apache-2.0`
  - `Requires-Dist` is exactly `httpx<1,>=0.27` and `anyio>=4.0`
  - the wheel is pure Python (`py3-none-any`)
  - there are no `tests/` or `specs/` files in the wheel
  It exits non-zero on failure. Add a call to it in the `build` job of `.github/workflows/ci.yml`

### Implementation for User Story 6

- [X] T055 [P] [US6] Write `README.md` with:
  - badges (PyPI, Python versions, licence, CI)
  - what FVS is, with links to the upstream repo and wiki
  - installation (`pip install fvs_client` / `uv add fvs_client`)
  - the quick start from quickstart.md §4
  - configuration through `FVS_BASE_URL`/`FVS_API_KEY`
  - an error-handling snippet
  - the supported FVS API version (1.0.x) and Python versions (3.11–3.15)
  - the 0.x stability note (breaking changes are flagged in CHANGELOG)
  - the licence (Apache-2.0)
- [X] T056 [P] [US6] Create `mkdocs.yml` (Material theme, `mkdocstrings[python]` with the Google docstring style, nav per research R16), along with:
  - `docs/index.md`, `docs/installation.md`, `docs/quickstart.md`, `docs/validation.md` and `docs/errors-and-retries.md`
  - `docs/reference/index.md`, using `::: fvs_client` to render the API reference
- [X] T057 [P] [US6] Create `.github/workflows/release.yml`, triggered on tags `v*`:
  - `test` job: calls `.github/workflows/ci.yml` through `workflow_call` (lint, types, full test matrix, coverage, audit)
  - `integration` job: calls `.github/workflows/integration.yml` through `workflow_call` with `secrets: inherit`. Without the secrets, T012 falls back to generated random keys, so the job still runs
  - `build` job, with `needs: [test, integration]`: `uv build`, `twine check --strict`, `scripts/check_dist.py dist/`, and upload the `dist/` artifact
  - `testpypi` job: environment `testpypi`, `permissions: id-token: write`, `pypa/gh-action-pypi-publish` with `repository-url: https://test.pypi.org/legacy/` and `attestations: true`
  - `smoke` job: install `fvs_client==<tag version>` from TestPyPI into a clean Python 3.11 venv and import it
  - `pypi` job: environment `pypi`, Trusted Publishing, `attestations: true`
  - `github-release` job: creates the release with notes extracted from the matching `CHANGELOG.md` section
- [X] T058 [P] [US6] Create `.github/workflows/docs.yml`, which builds `mkdocs build --strict` on PRs and deploys to GitHub Pages on pushes to `main`
- [X] T059 [US6] Add a `## [0.1.0] - Unreleased` entry to `CHANGELOG.md`, listing the features delivered so far with links to the spec, and document the release procedure (tag `vX.Y.Z` → release workflow) in `CONTRIBUTING.md`. Then run T053–T054 and `uv run mkdocs build --strict`, and confirm they pass

**Checkpoint**: The package is publishable, typed and documented, with all P1 stories done.

---

## Phase 6: User Story 3 - Use the SDK in asynchronous applications (Priority: P2)

**Goal**: `AsyncClient` has the same operations, options, results and errors as `Client`. `validate_many` runs on both clients, with bounded concurrency and per-item results in input order.

**Independent Test**: The US1 and US2 scenario suites pass, parametrised over both clients. `tests/parity/test_signatures.py` passes. `tests/scenarios/test_us3_async_batch.py` validates 100 resources (and 1,000 for SC-005), with in-order results, the concurrency limit respected, and no leaked connections.

### Tests for User Story 3 (write first, confirm FAIL)

- [X] T060 [P] [US3] Write `tests/parity/test_signatures.py`. For `Client`/`AsyncClient`, and for each sub-client pair that exists, it asserts:
  - the same public method names
  - identical parameter names, kinds and defaults (`inspect.signature`)
  - matching return annotations, after unwrapping `Coroutine`/`Awaitable`
  - `AsyncClient` exposes `aclose`/`__aenter__`/`__aexit__`, and `Client` exposes `close`/`__enter__`/`__exit__`
- [X] T061 [US3] Change the `client` fixture in `tests/conftest.py` to be parametrised over `["sync", "async"]`. It yields a uniform call adapter: for async it runs the coroutine on the anyio backend. Then update `tests/scenarios/test_us1_validate.py` and `tests/scenarios/test_us2_errors.py` to use it, so every US1 and US2 scenario runs on both clients
- [X] T062 [P] [US3] Write `tests/unit/test_transport_async.py`, mirroring T019 and the retry integration for `AsyncTransport`: the injected async sleep is awaited with the decided delay, exceptions are mapped, a caller-owned `httpx.AsyncClient` is not closed, and an owned one is closed by `aclose()` and `async with`
- [X] T063 [P] [US3] Write `tests/scenarios/test_us3_async_batch.py`:
  - `validate_many` on 100 resources plus one `"not fhir"` string → 101 entries in input order, with the last one an `InputError`
  - a mix of 200, 404 and 429 (retry disabled) responses → each slot holds its own result or error, and one failure does not cancel the others
  - the concurrency limit: with `concurrency=10`, the number of in-flight requests counted by the mock transport never exceeds 10
  - the same checks for the sync `Client.validate_many` (thread pool)
  - SC-005: 1,000 resources complete with 1,000 entries, and every opened mock connection or stream is closed

### Implementation for User Story 3

- [X] T064 [P] [US3] Implement `src/fvs_client/_async/transport.py`. `AsyncTransport(http_client: httpx.AsyncClient, settings, policy, sleep=anyio.sleep, clock=time.perf_counter)` is a line-for-line mirror of `SyncTransport.send`, using the shared `_requests`, `_parsing`, `_problems`, `_retry` and `_logging` modules
- [X] T065 [US3] Implement `src/fvs_client/_async/client.py`:
  - `AsyncClient`, with the same `__init__` signature as `Client` except that `http_client` is `httpx.AsyncClient | None`
  - `aclose`, `__aenter__`, `__aexit__` and a masked `__repr__`
  - `async def validate(...)`, with the same overloads as `Client.validate` (depends on T064)
- [X] T066 [US3] Implement `validate_many(resources, *, fhir_version, concurrency=8, **validate options)` on both clients:
  - **Async** (in `src/fvs_client/_async/client.py`): an `anyio.create_task_group()` plus `anyio.CapacityLimiter(concurrency)`
  - **Sync** (in `src/fvs_client/_sync/client.py`): `concurrent.futures.ThreadPoolExecutor(max_workers=concurrency)`, sharing the one `httpx.Client`
  - **Results**: a `list[ValidationResult | OperationOutcomeResult | RawResponse | FVSError]` in input order; each `FVSError` (including `InputError`) is captured into its slot, and only non-FVS exceptions propagate
  - **Argument checks**: `concurrency < 1` → `InputError`
- [X] T067 [US3] Export `AsyncClient` from `src/fvs_client/__init__.py`, extend the expected list in `tests/unit/test_public_api.py`, add `docs/async-and-batch.md` and add it to the `mkdocs.yml` nav, and add the new public API to `CHANGELOG.md` under `## [Unreleased]` → `### Added`. Then run T060–T063 and confirm they pass

**Checkpoint**: US1, US2, US3 and US6 work independently on both clients.

---

## Phase 7: User Story 4 - Manage IG packages and validator contexts (Priority: P2)

**Goal**: Admin automation through two sub-clients on both clients:
- `client.contexts`: `include`, `exclude` and `update`
- `client.packages`: `upload` (streamed), `register`, `update`, `dependencies`, and the deprecated `files`

**Independent Test**: `tests/scenarios/test_us4_admin.py` covers acceptance scenarios 1–6 on both clients, using MockTransport. `tests/integration/test_us4_admin.py` runs the quickstart §6 lifecycle on the live service: register → dependencies → include → validate with `ig` → update → exclude → validation refused.

### Tests for User Story 4 (write first, confirm FAIL)

- [X] T068 [P] [US4] Write `tests/unit/test_admin_inputs.py`:
  - **`AccessChange`**: "at least one field must be set"; `owner` must match "`^[A-Za-z0-9_-]{2,32}$`"; `terminology` with `packages.update` → `InputError`
  - **`register`**: "exactly one of `name` / `download_url`"; `version` "≤ 64 chars"
  - **`contexts.exclude`/`update`**: need an exact `name#version` or a two-IG key ("no `latest`", no version series) → otherwise `InputError`
  - **`contexts.include`**: accepts an exact version, `latest` or a series `N.x` / `N.x.x` / `N.N.x`; a two-IG tuple must not name the same `igPackageId` twice
  - **`upload`**: accepts an `os.PathLike` or a binary file object; a text-mode file → `InputError`
- [X] T069 [P] [US4] Write `tests/unit/test_requests_admin.py`, asserting every admin row of `contracts/http-mapping.md#operation-table`:
  - **`include`**: a single `IgRef` → JSON `{igPackageId, igPackageVersion}` (version omitted when `None`); a tuple → `{igPackages: [...]}`; `shareable`/`terminology` only when set
  - **`exclude`/`update`**: send `?ig=` with `#` → `%23` and `|` → `%7C`; `update` sends only the `AccessChange` fields that are set
  - **`upload`**: a `multipart/form-data` request with a `file` part (`application/gzip`, streamed from a file handle without reading it whole) and a `shareable` part `"true"`/`"false"`
  - **`register`**: sends JSON `{name, version, includeDependency, shareable}` or `{downloadUrl, includeDependency, shareable}`
  - **`packages.update`/`dependencies`/`files`**: path segments are encoded with `quote(seg, safe="")`
  - **`is_admin`**: true for include, exclude, both updates, upload and register; false for `dependencies` and `files`
- [X] T070 [P] [US4] Write `tests/unit/test_parsing_admin.py`, parsing each `tests/fixtures/admin/*.json` into `IncludeResult` (with `IncludedIg` items, `key` from `key.igPackage`, aliases, `requested_version`, revision, included, resolved, terminology, owner, shareable, warnings), `ExcludeResult`, `ContextAccessResult`, `IgPackageResult`, `PackageAccessResult`, `PackageDependencies` and `PackageFiles`. Assert every field from data-model.md, plus `raw`, `meta` and `to_dict()`
- [X] T071 [P] [US4] Write `tests/contract/test_admin_contract.py`, using `openapi-core`. Every built admin request and every admin fixture response validates against operations `validatorApiIncludeIg`, `validatorApiExcludeIg`, `validatorApiChangeIncludedIg`, `igPackageApiUploadIg`, `igPackageApiRegisterIg`, `igPackageApiChangeAccess`, `igPackageApiGetDependenciesGraph` and `igPackageApiGenerateConformanceReport`
- [X] T072 [P] [US4] Write `tests/scenarios/test_us4_admin.py` (on both clients through the `client` fixture), implementing spec US4 acceptance scenarios 1–6:
  1. `upload` of a temporary `.tgz` with `shareable=False`
  2. `register` with an exact version, `latest` and `1.2.x`
  3. `include` with a single IG and with two IGs
  4. `update` and `exclude`, with warnings reported
  5. a 403 → `PermissionDeniedError`
  6. `dependencies`
  Also cover:
  - **Admin retries**: a 503 then 200 on an admin operation is NOT retried by default; it IS retried with `retries=1`; a connect error on an admin operation is never retried
  - **Deprecated `files`**: `packages.files` emits a `DeprecationWarning` (`pytest.warns`)
- [X] T073 [P] [US4] Write `tests/integration/test_us4_admin.py` (uses `it_admin_client`; skipped if `FVS_IT_ADMIN_API_KEY` is unset), implementing the quickstart §6 lifecycle with `hl7.fhir.uv.ips#1.1.0`:
  - `register` → `dependencies` → `include`
  - validate with `ig=inc.key`, and assert `context.key == inc.key`
  - `contexts.update(AccessChange(shareable=True))` → `exclude`
  - validating again raises `BadRequestError` with `problem_type == ProblemType.INVALID_REQUEST`
  - the same admin call made with the validation key → `PermissionDeniedError`

### Implementation for User Story 4

- [X] T074 [P] [US4] Add the admin models to `src/fvs_client/models.py`: `IncludedIg`, `IncludeResult`, `ExcludeResult`, `ContextAccessResult`, `AccessChange` (`__post_init__`: "at least one field must be set" and `owner` matching `^[A-Za-z0-9_-]{2,32}$`), `IgPackageResult`, `PackageAccessResult`, `PackageDependencies` and `PackageFiles`. Every field is named and typed as in data-model.md
- [X] T075 [P] [US4] Add to `src/fvs_client/_inputs.py`:
  - `check_include_ig`, `check_exact_ig` and `check_register_args`, enforcing the T068 rules
  - `prepare_archive(archive) -> (filename, binary stream, should_close)` for streaming uploads
- [X] T076 [US4] Implement `build_include`, `build_exclude`, `build_context_update`, `build_upload`, `build_register`, `build_package_update`, `build_dependencies` and `build_files` in `src/fvs_client/_requests.py`, following `contracts/http-mapping.md`. Each sets `is_admin` per T069 (depends on T074, T075)
- [X] T077 [US4] Implement the parsers `parse_include`, `parse_exclude`, `parse_context_access`, `parse_ig_package`, `parse_package_access`, `parse_dependencies` and `parse_files` in `src/fvs_client/_parsing.py` (depends on T074)
- [X] T078 [US4] Implement the sync sub-clients `Contexts` (`include`, `exclude`, `update`) and `Packages` (`upload`, `register`, `update`, `dependencies`, `files`) in `src/fvs_client/_sync/client.py`, wired up as `Client.contexts` and `Client.packages`:
  - signatures follow `contracts/public-api.md#validator-contexts-story-4-admin` and `#ig-packages-story-4-clientpackages`
  - each method has `raw` `@overload`s, and the admin methods take a `retries: int | None` keyword
  - `files` calls `warnings.warn(..., DeprecationWarning, stacklevel=2)`
  - upload streams are closed when the SDK opened them (depends on T076, T077)
- [X] T079 [US4] Implement the async sub-clients `AsyncContexts` and `AsyncPackages` in `src/fvs_client/_async/client.py`, mirroring T078, as `AsyncClient.contexts` and `AsyncClient.packages`. The async upload streams the file through an async iterator over the binary handle (depends on T065, T078)
- [X] T080 [US4] Export `AccessChange`, `IncludedIg`, `IncludeResult`, `ExcludeResult`, `ContextAccessResult`, `IgPackageResult`, `PackageAccessResult`, `PackageDependencies` and `PackageFiles` from `src/fvs_client/__init__.py`, and extend `tests/unit/test_public_api.py`. Add `docs/packages-and-contexts.md` to the docs and the `mkdocs.yml` nav, and add the new public API to `CHANGELOG.md` under `## [Unreleased]` → `### Added`, then run T068–T073 and T060 (parity) and confirm they pass

**Checkpoint**: Admin automation works on both clients, independently of US5.

---

## Phase 8: User Story 5 - Check service health (Priority: P3)

**Goal**: `client.health.check()`, `.liveness()` and `.readiness()` return structured reports with no API key needed. A 503 with a report body is returned (`is_ready`/`is_healthy` False), not raised.

**Independent Test**: `tests/scenarios/test_us5_health.py` covers acceptance scenarios 1–3 on both clients, plus a client with no key and no `Authorization` header. `tests/integration/test_us5_health.py` runs against the live service.

### Tests for User Story 5 (write first, confirm FAIL)

- [X] T081 [P] [US5] Write `tests/unit/test_parsing_health.py`:
  - **`LivenessReport`**: `timestamp` is converted from epoch milliseconds to a UTC `datetime`
  - **`ReadinessReport`**: from `readiness_up.json` and `readiness_down.json`, covering `status`, `timestamp`, `catalog_revision`, `reasons`, `versions` (kept as a mapping) and `is_ready`
  - **`HealthReport`**: from `health_up.json` and `health_down.json`, covering:
    - `database` (from `postgres`: status, response time, error)
    - `readiness`
    - `served_fhir_versions` (from `fhirVersions.served`)
    - `inactive_contexts`: count, private count, items (`fhirVersion`, `igPackage`, `igPackages`, aliases, owner, reason)
    - `terminology_allowlist`, per version: `source` (one of `registry`/`stored-registry`/`built-in`), `fetched_at`, `registry_last_update`, `servers`, `reason`
    - `acl_enabled` (from `security.aclSecurity == "enabled"`)
    - `is_healthy`
  - **503 rule**: a 503 with a JSON report body → report returned; a 503 with an `application/problem+json` body or no body → `ServiceUnavailableError`
- [X] T082 [P] [US5] Write `tests/contract/test_health_contract.py`, using `openapi-core`: the health request and fixture responses validate against operations `healthApiHealth`, `healthApiLiveness` and `healthApiReadiness`
- [X] T083 [P] [US5] Write `tests/scenarios/test_us5_health.py` (on both clients), implementing spec US5 acceptance scenarios 1–3:
  1. a ready service → `is_ready` True, with the per-version info
  2. a not-ready 503 → report returned with its reasons, no exception
  3. `check()` reports the database status, served versions, terminology source and `acl_enabled`
  Also: a client created without `api_key` sends no `Authorization` header and succeeds; the default safe-operation retry applies to `liveness` when connections fail
- [X] T084 [P] [US5] Write `tests/integration/test_us5_health.py`: on the live service, `liveness`, `readiness` (`is_ready` True) and `check()` (lists `R4` in `served_fhir_versions`) all succeed with a client created without an API key

### Implementation for User Story 5

- [X] T085 [P] [US5] Add the health models to `src/fvs_client/models.py`:
  - `StrEnum`s `AllowlistSource` (`registry`, `stored-registry`, `built-in`) and `ContextState` (`ACTIVE`, `BUILDING`, `STALE`, `ABSENT`)
  - dataclasses `DatabaseHealth`, `InactiveContext`, `InactiveContexts`, `AllowlistState`, `LivenessReport`, `ReadinessReport` (with an `is_ready` property) and `HealthReport` (with an `is_healthy` property), with fields as in data-model.md
- [X] T086 [US5] Implement `build_health`, `build_liveness` and `build_readiness` in `src/fvs_client/_requests.py` (`GET`, `Accept: application/json`, `is_admin=False`). Implement `parse_liveness`, `parse_readiness` and `parse_health` in `src/fvs_client/_parsing.py`. Add a `report_on_503=True` path to `finalize`, so that a 503 with a non-problem JSON body is parsed and returned, while a 503 problem or empty body raises (depends on T085)
- [X] T087 [US5] Implement the sync `Health` sub-client (`check`, `liveness`, `readiness`, each with `raw` overloads) as `Client.health` in `src/fvs_client/_sync/client.py`, and the async `AsyncHealth` sub-client as `AsyncClient.health` in `src/fvs_client/_async/client.py` (depends on T086)
- [X] T088 [US5] Export `HealthReport`, `ReadinessReport` and `LivenessReport` from `src/fvs_client/__init__.py`, and complete the expected list in `tests/unit/test_public_api.py` so it equals the full `contracts/public-api.md` export list. Add `docs/health.md` to the docs and the `mkdocs.yml` nav, and add the new public API to `CHANGELOG.md` under `## [Unreleased]` → `### Added`, then run T081–T084 and T060 and confirm they pass

**Checkpoint**: All six user stories work independently on both clients.

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: The cross-story quality gates (SC-004, SC-006, SC-007, SC-009), the remaining docs, and release readiness.

- [X] T089 [P] Write `tests/unit/test_no_secret_leak.py` (SC-009). Configure `api_key="s3cr3t-key-value"` and send every public operation on both clients through `MockTransport`, returning success, a 401, a 429 and a 500. Then assert the key does not appear in:
  - `repr(client)`, `repr(result)`, `str(error)`, `repr(error)` or `error.response`
  - the captured log text at DEBUG level

  Also assert that an attempt to pass the key through `extra_headers` is refused before anything is sent
- [X] T090 [P] Write `tests/perf/test_overhead.py` (marker `perf`, SC-004). Using an in-process `MockTransport` that returns the `patient_invalid.json` fixture instantly, the median SDK time per `validate()` call for a 90 KB resource dict over 500 calls must be under 5 ms. Add an opt-in `perf` job to `.github/workflows/ci.yml`
- [X] T091 [P] Add `docs/raw-responses.md` (raw mode, `RawResponse`, `.raw` on results, `to_dict()`) and a CHANGELOG link page to `docs/`, and update the `mkdocs.yml` nav
- [X] T092 [P] Add Hypothesis property tests in `tests/unit/test_properties.py`:
  - `IgRef.parse(str(ref)) == ref` for generated valid refs
  - `short_name` of `<any https base>/problems/<slug>` equals `slug`
  - `check_validation_options` never accepts more than 10 distinct profiles
- [X] T093 Run the full gate locally and fix any findings in the source files they point to: `uv run ruff check . && uv run ruff format --check . && uv run mypy --strict src tests && uv run pyright && uv run pytest --cov --cov-branch --cov-fail-under=90`. Branch coverage must be ≥ 90% (SC-006)
- [X] T094 Run `quickstart.md` §1–§8 end to end against a local FVS 1.0.0 (Docker Compose). Record the results and any differences from the expected outcomes in `specs/001-fvs-python-sdk/quickstart.md` under a new "Validation log" heading, and file follow-up tasks for any mismatch, including whether the server splits comma-separated `profile` values (research R13)
- [X] T095 Finalise `CHANGELOG.md` `## [0.1.0]`: list every feature, the supported FVS API 1.0.x and Python 3.11–3.15. Check that the `README.md` examples match the final API by running them as doctests (add a `--doctest-glob=README.md` invocation to the `test` job in `.github/workflows/ci.yml`)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies. T013 depends on T002–T007.
- **Foundational (Phase 2)**: Depends on Setup. It BLOCKS all user stories.
- **US1 (Phase 3)**: Depends on Foundational only. This is the MVP.
- **US2 (Phase 4)**: Depends on Foundational. Its scenario tests call `validate` as the simplest operation, so it is easiest after US1. Its retry and error code (T048–T051) does not depend on US1.
- **US6 (Phase 5)**: Depends on Foundational. Its packaging and release tasks are independent of US1/US2, but the README and docs content (T055, T056) assume US1 and US2 exist.
- **US3 (Phase 6)**: Depends on US1 (it mirrors `validate`) and on US2's transport retry (T049). T061 edits the US1 and US2 scenario files.
- **US4 (Phase 7)**: Depends on Foundational for the sync part (T074–T078); its scenario tests run on the sync client until US3's T061 adds the async client. The async part (T079) depends on US3's T064 and T065.
- **US5 (Phase 8)**: Depends on Foundational for the sync part. The async part of T087 depends on US3's T065.
- **Polish (Phase 9)**: Depends on all stories.

### User Story Dependency Graph

```text
Setup → Foundational ─┬─> US1 (MVP) ─┬─> US3 (async) ─┬─> US4 async part (T079)
                      │              │                └─> US5 async part (T087)
                      ├─> US2 ───────┘
                      ├─> US6 (packaging/docs; content assumes US1+US2)
                      ├─> US4 sync part (T074–T078)
                      └─> US5 sync part (T085–T086)
                                         all ──> Polish
```

### Within Each User Story

- Test tasks first; confirm they FAIL (Constitution III)
- Models → input checks → request builders → parsers → client methods → exports/docs
- Same-file tasks (`models.py`, `_requests.py`, `_parsing.py`, `_sync/client.py`, `_async/client.py`, `__init__.py`) run in task-ID order, never in parallel

### Parallel Opportunities

- **Setup**: T004–T012 are all [P].
- **Foundational**: tests T014–T020 are all [P]; T021, T022, T024 and T025 are [P].
- **US1**: tests T031–T038 are all [P]; T039 and T040 are [P].
- **US2**: tests T045–T047 are [P].
- **US6**: T053–T058 are mostly [P]. US6 can be worked on alongside US1/US2 by a second developer.
- **US3**: T060, T062 and T063 are [P]; T064 is [P].
- **US4**: tests T068–T073 are all [P]; T074 and T075 are [P]. The US4 sync part can run alongside US3.
- **US5**: tests T081–T084 are all [P]. The US5 sync part can run alongside US3 and US4.
- **Polish**: T089–T092 are [P].

---

## Parallel Example: User Story 1

```bash
# All US1 tests together (different files):
Task: "T031 Write tests/unit/test_inputs.py"
Task: "T032 Write tests/unit/test_validation_options.py"
Task: "T033 Write tests/unit/test_requests_validate.py"
Task: "T034 Write tests/unit/test_parsing_validation.py"
Task: "T035 Write tests/contract/test_validate_contract.py"
Task: "T036 Write tests/scenarios/test_us1_validate.py"
Task: "T037 Write tests/integration/test_us1_validate.py"
Task: "T038 Write tests/typing/test_validate_overloads.py"

# Then the independent implementation pieces:
Task: "T039 Add validation models to src/fvs_client/models.py"
Task: "T040 Implement src/fvs_client/_inputs.py"
```

## Parallel Example: User Story 4

```bash
Task: "T068 tests/unit/test_admin_inputs.py"
Task: "T069 tests/unit/test_requests_admin.py"
Task: "T070 tests/unit/test_parsing_admin.py"
Task: "T071 tests/contract/test_admin_contract.py"
Task: "T072 tests/scenarios/test_us4_admin.py"
Task: "T073 tests/integration/test_us4_admin.py"
# then
Task: "T074 admin models in src/fvs_client/models.py"
Task: "T075 admin input checks in src/fvs_client/_inputs.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Setup → Phase 2: Foundational
2. Phase 3: US1 (sync `validate` with typed results and basic typed errors)
3. **STOP and VALIDATE**: run the US1 scenario tests and quickstart §4 against a local FVS
4. Optionally publish `0.1.0a1` to TestPyPI as a preview

### Incremental Delivery

1. Setup + Foundational → foundation ready
2. US1 → MVP (validation)
3. US2 → production-grade errors and retries
4. US6 → publishable package plus docs, then cut `v0.1.0rc1` on TestPyPI
5. US3 → async client and batch validation
6. US4 → admin automation
7. US5 → health checks
8. Polish → tag `v0.1.0` → release workflow publishes to PyPI

### Parallel Team Strategy

- Developer A: US1 → US3 → US4 async part → US5 async part
- Developer B: US2 → US4 sync part → US5 sync part
- Developer C: US6 (packaging, release, docs) → Polish docs

---

## Notes

- [P] = different files and no dependency on an unfinished task; tasks touching the same file are never [P].
- The story labels map to spec.md user stories US1–US6. Phases follow priority order, not story number.
- Commit after each task or logical group (Conventional Commits), and stop at any checkpoint to validate the story on its own.
- Any change to `contracts/fvs-openapi-v1.0.0.yaml` is its own PR (constitution workflow).
