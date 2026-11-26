# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html). While the version is 0.x,
breaking changes can happen in any minor release and are marked **BREAKING**.

## [Unreleased]

## [0.1.0] - Unreleased

First release, supporting FHIR Validation Service API **1.0.x** on Python **3.11–3.15**. Specification:
[`specs/001-fvs-python-sdk/spec.md`](specs/001-fvs-python-sdk/spec.md).

### Added

- `Client.validate()`: validate a resource given as a dict, JSON/XML `str`/`bytes`, or a file
  (streamed), for STU3/R4/R4B/R5, with an optional IG (single or two-IG), extra profiles and a
  per-request terminology server/mode. Returns `ValidationResult`, a FHIR `OperationOutcome`
  (JSON or XML) or the `RawResponse` (`raw=True`).
- Local checks of the service's documented limits (`InputError`, nothing sent).
- Typed errors under `FVSError`, carrying the RFC 9457 problem (all 27 documented problem
  types), request id and rate-limit information.
- Bounded automatic retries for 429/503 (honouring `Retry-After`) and connection failures.
- `AsyncClient`: the same API as `Client` for asyncio and trio applications.
- `validate_many()` on both clients: concurrent batch validation with a concurrency limit, one
  result or error per input in input order.
- `client.contexts` (`include`, `exclude`, `update`) and `client.packages` (`upload`,
  `register`, `update`, `dependencies`, deprecated `files`) for IG administration, with
  `AccessChange` and typed results; administrative calls are not retried unless asked.
- `client.health` (`check`, `liveness`, `readiness`): typed reports, no API key needed; a 503
  with a report is returned (`is_ready`/`is_healthy` false) instead of raised.
- Immutable, typed result models with `to_dict()` and the original body in `raw`.
- Package metadata: Apache-2.0, `py.typed`, PEP 621/639; docs site; release by tag with PyPI
  Trusted Publishing.
