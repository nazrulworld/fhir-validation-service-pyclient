<!--
Sync Impact Report
==================
Version change: (unversioned template) → 1.0.0
Bump rationale: first ratification; every placeholder replaced with concrete governance.

Principles (template slot → adopted title):
- [PRINCIPLE_1_NAME] → I. Contract-Faithful SDK
- [PRINCIPLE_2_NAME] → II. Typed, Stable Public API
- [PRINCIPLE_3_NAME] → III. Test-First, Contract-Verified (NON-NEGOTIABLE)
- [PRINCIPLE_4_NAME] → IV. Single Transport (httpx), Sync/Async Parity
- [PRINCIPLE_5_NAME] → V. Secure and Private by Default
- (added) VI. Simplicity and Minimal Dependencies

Added sections:
- Technology & Packaging Standards (was [SECTION_2_NAME])
- Development Workflow & Quality Gates (was [SECTION_3_NAME])
- Governance (filled)

Removed sections: none

Templates reviewed (not modified by this command; they read the constitution at runtime):
- .specify/templates/plan-template.md ("Constitution Check" gate) ✅ compatible
- .specify/templates/spec-template.md ✅ compatible
- .specify/templates/tasks-template.md ✅ compatible (test-first ordering matches Principle III)
- .specify/templates/checklist-template.md ✅ compatible

Existing artifacts to re-check:
- specs/001-fvs-python-sdk/spec.md: aligned (Python 3.11 minimum, httpx, fvs_client, typed API,
  no API key leakage). Its checklist note 4 ("constitution not filled") is now outdated.

Deferred TODOs: none
-->

# fvs_client Constitution

## Core Principles

### I. Contract-Faithful SDK

The upstream FHIR Validation Service OpenAPI contract
(`src/main/resources/openapi.yaml` in nazrulworld/fhir-validation-service) is the single source of
truth for endpoints, parameters, limits, headers and problem types.

- Every SDK operation MUST map to a documented service operation; the SDK MUST NOT invent
  server behaviour, hide documented response data, or reinterpret service outcomes (e.g. a
  completed validation with errors is a result, not an exception).
- Each release MUST state which service API version(s) it supports; the vendored contract
  snapshot used for tests MUST be pinned and updated deliberately.
- Client-side checks MAY reject input early only where the contract documents the same limit.
- Unknown response fields MUST be tolerated and kept accessible (forward compatibility).

Rationale: an SDK that drifts from the service misleads users about validation results, which
in healthcare contexts can be harmful.

### II. Typed, Stable Public API

- The package MUST ship `py.typed`, and the whole public API MUST pass strict static type checking
  (mypy `--strict` and pyright strict) with zero errors.
- The public API is exactly what is exported from `fvs_client` (and documented sub-modules);
  everything else MUST be private (`_`-prefixed modules or names).
- Releases MUST follow Semantic Versioning: breaking changes to the public API only in a MAJOR
  release, after at least one MINOR release with a `DeprecationWarning` (exempt while < 1.0.0,
  where breaking changes MUST still be listed in the changelog).
- Every public class, function and error MUST have a docstring and appear in the API reference.
- Errors MUST derive from one SDK base exception, with distinct categories callers can catch.

Rationale: downstream applications and pipelines rely on the SDK's shapes; types and semver
make breakage visible before it reaches production.

### III. Test-First, Contract-Verified (NON-NEGOTIABLE)

- Tests MUST be written before or alongside the code they cover and MUST fail before the
  implementation exists (red → green → refactor).
- Unit tests MUST mock HTTP at the transport level (no real network) and cover every operation,
  every documented error status/problem type, retry behaviour and input-limit checks.
- Contract tests MUST verify requests and parsed responses against the pinned OpenAPI snapshot.
- Integration tests MUST run against the upstream service container in CI for every release,
  and MAY be skipped locally when no service is available.
- Line + branch coverage MUST stay ≥ 90%; a change that lowers it MUST justify why in review.
- The sync and async clients MUST be exercised by the same scenario suite.

Rationale: correctness of a validation client is only provable by tests tied to the contract.

### IV. Single Transport (httpx), Sync/Async Parity

- All communication with the service MUST go through `httpx`; no other HTTP library may be a
  runtime dependency.
- The SDK MUST provide a synchronous and an asynchronous client with identical operations,
  parameters, results and errors; behaviour MUST NOT diverge except in the sync/async call style.
  Shared logic (request building, response parsing, error mapping) MUST live in one place used by
  both.
- Clients MUST accept a caller-supplied `httpx` client/transport, MUST support context managers,
  and MUST release connections on close.
- Timeouts MUST always be set (no unbounded waits); retries MUST be bounded, honour
  `Retry-After`, and never repeat a state-changing call after a connection failure or timeout.

Rationale: one transport keeps behaviour predictable; parity prevents a second-class client.

### V. Secure and Private by Default

- API keys MUST never appear in logs, exception messages, `repr`/`str` output, or test snapshots.
- Resource bodies (which may contain patient data) MUST NOT be logged by the SDK at any level.
- TLS verification MUST be on by default; turning it off MUST be an explicit, documented choice.
- Logging MUST use the standard `logging` module under the `fvs_client` logger and be silent by
  default (`NullHandler`).
- Dependencies MUST be scanned for known vulnerabilities in CI; releases MUST be published via
  PyPI Trusted Publishing (OIDC) with build provenance/attestations, never with long-lived tokens.

Rationale: the SDK handles credentials and health data; leaks are not recoverable.

### VI. Simplicity and Minimal Dependencies

- Runtime dependencies MUST be limited to `httpx` plus what is strictly necessary; each one
  MUST be justified in the plan and declared with a compatible lower bound and no needless
  upper cap.
- The SDK passes FHIR resources as plain data (dict / str / bytes); it MUST NOT require a FHIR
  model library. Optional integrations MAY be offered only as extras.
- Prefer the smallest design that satisfies the spec (YAGNI); added abstraction layers MUST be
  justified in the plan's Complexity Tracking.

Rationale: a small dependency surface eases adoption, auditing and long-term maintenance.

## Technology & Packaging Standards

- **Distribution name**: `fvs_client` on PyPI; import package `fvs_client`.
- **Python**: `requires-python = ">=3.11"`; CI MUST test 3.11 and every newer stable CPython
  release on Linux, macOS and Windows. Language features newer than 3.11 MUST NOT be used
  without a fallback.
- **Project metadata**: a single `pyproject.toml` (PEP 621) with a PEP 517 build backend; `src/`
  layout; no `setup.py`. Licence declared with an SPDX expression and shipped in the
  distributions (OSI-approved).
- **Tooling**: `uv` for environments and locking; `ruff` for lint and format; mypy and pyright for
  types; `pytest` (+ `pytest-asyncio`/`anyio`) with coverage; `pre-commit` hooks mirroring CI.
- **Artifacts**: every release publishes an sdist and a pure-Python wheel, built in CI, checked
  with `twine check` (or equivalent) and smoke-tested by installing into a clean environment.
- **Versioning & changelog**: SemVer; `CHANGELOG.md` in Keep a Changelog format; releases are cut
  from annotated tags `vX.Y.Z` only.
- **Documentation**: README with install + quick start; hosted docs with guides per operation
  group, error handling, async usage and an API reference generated from docstrings.

## Development Workflow & Quality Gates

- All changes go through a pull request; direct pushes to the default branch are not allowed.
- A PR MUST pass these gates before merge: ruff (lint + format check), mypy strict, pyright
  strict, unit + contract tests on the full Python/OS matrix, coverage ≥ 90%, dependency
  vulnerability scan, and package build check.
- Any change to the public API or behaviour MUST update docs, docstrings and `CHANGELOG.md`
  (Unreleased) in the same PR.
- Conventional Commits SHOULD be used for commit messages to keep history and changelog readable.
- Feature work follows Spec Kit: spec → plan (with Constitution Check) → tasks → implement;
  the plan MUST record any principle deviation in Complexity Tracking with justification.
- Updating the pinned service contract snapshot is its own PR that lists the upstream changes and
  the SDK changes they need.

## Governance

- This constitution overrides other project practices and guides. Where they conflict, this
  document wins until it is amended.
- **Amendments**: proposed in a PR that edits this file, states the version bump and its reason,
  and updates any affected specs/plans. A maintainer approves and merges it.
- **Versioning policy**: MAJOR for removing or redefining a principle in an incompatible way;
  MINOR for a new principle/section or materially expanded guidance; PATCH for wording and
  clarifications.
- **Compliance**: every `/speckit-plan` MUST pass the Constitution Check before Phase 0 and
  again after design; reviewers MUST verify compliance on every PR; unjustified complexity or
  deviations are grounds to block a merge.
- The constitution SHOULD be reviewed at least before each MAJOR or MINOR SDK release.

**Version**: 1.0.0 | **Ratified**: 2026-11-26 | **Last Amended**: 2026-11-26
