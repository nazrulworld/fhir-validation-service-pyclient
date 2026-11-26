# Implementation Plan: FHIR Validation Service Python SDK (`fvs_client`)

**Branch**: `001-fvs-python-sdk` | **Date**: 2026-11-26 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-fvs-python-sdk/spec.md`

## Summary

Build `fvs_client`, a typed Python 3.11+ SDK (Apache-2.0, first release 0.1.0) for the FHIR
Validation Service 1.0 HTTP API. It covers:
- validation, with three result formats and a raw mode
- validator-context and IG-package administration
- health checks
- typed RFC 9457 problem errors
- bounded retries that honour `Retry-After`
- a concurrent `validate_many`

Design:
- A **sans-I/O core** (request builders, response parsers, error mapping and retry decisions as
  pure functions) shared by thin `httpx.Client` / `httpx.AsyncClient` front ends, which
  guarantees sync/async parity.
- Results are frozen standard-library dataclasses that keep the original body.
- The only runtime dependencies are `httpx` and `anyio`.
- Packaging uses `pyproject.toml` with hatchling and hatch-vcs (version from tags), uv, ruff,
  mypy and pyright in strict mode, pytest, and PyPI Trusted Publishing.

## Technical Context

**Language/Version**: Python ≥ 3.11 (CI: CPython 3.11–3.15)

**Primary Dependencies**:
- Runtime: `httpx>=0.27,<1`, `anyio>=4.0`
- Build: `hatchling`, `hatch-vcs`
- Dev: uv, ruff, mypy, pyright, pytest, pytest-cov, openapi-core, hypothesis, mkdocs-material,
  mkdocstrings[python], pre-commit, pip-audit

**Storage**: N/A (stateless client library)

**Testing**:
- pytest with anyio's plugin (asyncio, plus trio in one job)
- `httpx.MockTransport` unit tests
- openapi-core contract tests against the pinned `contracts/fvs-openapi-v1.0.0.yaml`
- Docker Compose integration tests against `ghcr.io/nazrulworld/fhir-validation-service:1.0.0`

**Target Platform**: Any OS running CPython 3.11 or newer (CI: Linux, macOS, Windows); pure-Python wheel

**Project Type**: Library (SDK) published to PyPI as `fvs_client`

**Performance Goals**:
- Under 5 ms SDK overhead per validation call for resources under 100 KB (SC-004)
- `validate_many` over 1,000 resources with no lost results or leaked connections (SC-005)

**Constraints**:
- Every HTTP call goes through httpx.
- The API key and resource bodies are never logged or shown in repr.
- Timeouts are always bounded (default 60 s, 10 s connect).
- File inputs and IG archives are streamed.
- Public API passes mypy and pyright strict with zero errors; coverage ≥ 90%.

**Scale/Scope**:
- 12 wrapped service operations across 4 groups
- About 25 public model and enum types
- 17 error classes
- An estimated 2.5–3.5k lines of source plus a similar amount of tests

All Technical Context items are resolved in [research.md](./research.md) (R1–R18); none are marked NEEDS CLARIFICATION.

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle / Standard | Requirement | Plan compliance | Pre-research | Post-design |
|---|---|---|---|---|
| I. Contract-Faithful | Pinned contract; no invented behaviour; tolerate unknown fields; state the supported API | `contracts/fvs-openapi-v1.0.0.yaml` pinned with its SHA; [http-mapping.md](./contracts/http-mapping.md) maps every operation; `raw` kept on every model; `SUPPORTED_API = "1.0"`; contract/wiki differences recorded (research R1) | ✅ | ✅ |
| II. Typed, Stable API | `py.typed`; strict mypy and pyright; private by default; semver; docstrings; single base error | `src/fvs_client/` exposes `__all__`, and every other module is `_`-prefixed; `@overload` keeps `raw` and `result_format` types precise; `FVSError` root; 0.x breaking changes recorded in the changelog | ✅ | ✅ |
| III. Test-First (NON-NEGOTIABLE) | Tests before code; transport-level mocks; contract tests; integration in CI; ≥ 90% coverage; shared sync/async suite | Research R15: unit tests on MockTransport, openapi-core contract tests, Compose integration tests, `--cov-fail-under=90`, scenario suites parametrised over both clients; tasks will order tests first | ✅ | ✅ |
| IV. httpx-only, Sync/Async Parity | httpx only; identical clients; shared logic; caller-supplied client; bounded timeouts and retries | Sans-I/O core (R6); parity test; `http_client=` parameter; default `Timeout(60, connect=10)`; `RetryPolicy` honours `Retry-After` and never retries admin calls after a connection failure or timeout (R10) | ✅ | ✅ |
| V. Secure & Private | No keys or bodies in logs or repr; TLS on; NullHandler logging; vulnerability scan; Trusted Publishing | `_SecretStr`, header redaction, no body logging (R11, R18); pip-audit plus Dependabot; release through OIDC with attestations (R17) | ✅ | ✅ |
| VI. Simplicity / Minimal deps | httpx plus what is strictly necessary, each justified; no FHIR model library; YAGNI | Two runtime dependencies (httpx, anyio), both justified in R3; plain-data inputs and outputs; no codegen or extra layers | ✅ | ✅ |
| Packaging standards | `fvs_client`; `requires-python>=3.11`; PEP 621 + PEP 517; `src/` layout; SPDX licence; uv/ruff/mypy/pytest/pre-commit; sdist + wheel; `twine check`; Keep a Changelog; tag releases; hosted docs | R2, R4, R5, R16, R17 | ✅ | ✅ |
| Workflow gates | PR-only; lint, types, tests on the full matrix, coverage, vulnerability scan, build check | `ci.yml` (R17) | ✅ | ✅ |

**Gate result**: PASS. No violations, so Complexity Tracking stays empty. One item is
recorded for transparency: the `httpx<1` upper cap is a *justified* cap under Principle VI
(a known breaking 1.0 release; research R3), not a deviation.

## Project Structure

### Documentation (this feature)

```text
specs/001-fvs-python-sdk/
├── plan.md                         # This file
├── research.md                     # Phase 0: decisions R1–R18
├── data-model.md                   # Phase 1: models, enums, validation rules
├── quickstart.md                   # Phase 1: end-to-end validation guide
├── contracts/
│   ├── public-api.md               # Python API contract (exports, signatures, errors)
│   ├── http-mapping.md             # SDK op ↔ HTTP, header use, error map, retry and pre-flight tables
│   └── fvs-openapi-v1.0.0.yaml     # pinned upstream contract (tag v1.0.0)
├── checklists/requirements.md
└── tasks.md                        # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root)

```text
pyproject.toml                # PEP 621 metadata, hatchling + hatch-vcs, tool configs (ruff, mypy, pyright, pytest, coverage)
uv.lock
LICENSE                       # Apache-2.0
NOTICE
README.md
CHANGELOG.md                  # Keep a Changelog
CONTRIBUTING.md
SECURITY.md
mkdocs.yml
.pre-commit-config.yaml
.github/
├── dependabot.yml
└── workflows/
    ├── ci.yml                # lint, types, test matrix, coverage, build, twine check, smoke install, pip-audit
    ├── integration.yml       # Compose-based tests vs ghcr.io/nazrulworld/fhir-validation-service:1.0.0
    ├── release.yml           # on v* tag: build → TestPyPI → smoke → PyPI (Trusted Publishing) → GitHub release
    └── docs.yml              # MkDocs → GitHub Pages
docs/
├── index.md  installation.md  quickstart.md  validation.md  packages-and-contexts.md
├── health.md  errors-and-retries.md  async-and-batch.md  raw-responses.md
└── reference/                # mkdocstrings API reference
src/fvs_client/
├── __init__.py               # public re-exports, __all__, __version__, SUPPORTED_API
├── py.typed
├── _version.py               # generated by hatch-vcs
├── models.py                 # public dataclasses + StrEnums (data-model.md)
├── errors.py                 # public error hierarchy
├── _config.py                # env resolution, _SecretStr, defaults, RetryConfig
├── _requests.py              # sans-I/O request builders → RequestSpec
├── _inputs.py                # resource sniffing/streaming, IgRef/option checks
├── _parsing.py               # body/header → models, ResponseMeta, RawResponse
├── _problems.py              # Problem parsing, ProblemType catalogue, status → error mapping
├── _retry.py                 # RetryPolicy decisions (pure)
├── _logging.py               # logger, redaction helpers
├── _sync/
│   ├── client.py             # Client + Contexts/Packages/Health sub-clients
│   └── transport.py          # send loop: httpx.Client + time.sleep
└── _async/
    ├── client.py             # AsyncClient + sub-clients
    └── transport.py          # send loop: httpx.AsyncClient + anyio.sleep
tests/
├── conftest.py               # MockTransport factories, both-clients fixture, fixture loader
├── fixtures/                 # JSON/XML bodies from contract + wiki examples
├── unit/                     # inputs, requests, parsing, problems, retry, models, config/secrets, logging
├── contract/                 # requests & fixture responses validated against fvs-openapi-v1.0.0.yaml
├── parity/                   # Client vs AsyncClient signature parity
├── scenarios/                # story-level suites run on both clients via MockTransport
├── integration/              # @pytest.mark.integration, needs FVS_IT_BASE_URL
├── typing/                   # assert_type checks run by mypy/pyright (SC-007)
└── perf/                     # @pytest.mark.perf overhead benchmark (SC-004)
scripts/
└── check_dist.py             # wheel/sdist metadata & contents gate (US6)
```

**Structure Decision**: A single-package library in `src/` layout. The private sans-I/O
modules hold all logic. `_sync/` and `_async/` hold only the send loops and method wrappers,
which keeps parity checkable and coverage high. Tests are split by kind so CI can run the
unit, contract and parity tiers on the full matrix, and the integration tier on Linux with
Docker.

## Complexity Tracking

No constitution violations, so nothing to justify.
