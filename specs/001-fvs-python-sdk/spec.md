# Feature Specification: FHIR Validation Service Python SDK (`fvs_client`)

**Feature Branch**: `001-fvs-python-sdk`

**Created**: 2026-11-26

**Status**: Draft

**Input**: User description: "This project is about to build a python based SDK to communicate & usages of fhir validation service https://github.com/nazrulworld/fhir-validation-service. Base principles: 1. Use the best software development practices, modern python publishing practice 2. Minimum python version is 3.11 3. Use 'httpx' for all communication to fhir validation server. 4. pypi package name would be 'fvs_client'"

## Context

The FHIR Validation Service (FVS) is an HTTP service that validates FHIR resources (STU3, R4, R4B, R5) against the core specification and against stored Implementation Guide (IG) packages. Its published contract (OpenAPI 3.0.3, service version 1.0.0) offers four groups of operations:

- **Validation**: validate one resource for a FHIR version, optionally against one IG (or a pair of IGs), extra profiles, and a per-request terminology setting. The result comes back as a simple summary (valid flag plus messages) or as a FHIR OperationOutcome (JSON or XML).
- **Validator contexts** (admin): include, exclude or change (sharing, ownership, terminology) the pre-built validator context for an IG version under a FHIR version.
- **IG packages**: upload a package archive, register (fetch) a package from a registry or URL, change a package's sharing or ownership, and read a package's declared dependencies.
- **Health**: overall health, liveness and readiness reports.

Every error is a structured problem document (RFC 9457) with a machine-readable `type`, and every response carries a request id. Access uses bearer API keys with two roles (VALIDATE, ADMIN). Validation requests can be rate limited (429 with a retry delay and rate-limit headers).

This feature delivers a Python SDK, published to PyPI as `fvs_client`, that lets Python developers use all of these operations without hand-crafting HTTP requests.

## Clarifications

### Session 2026-11-26

- Q: Should the first version include a command-line tool, or stay a Python-only library? → A: Library only in v1; a command-line tool is a later, separate feature.
- Q: Should the SDK accept/return objects from a FHIR model library (e.g. `fhir.resources`) as well as plain data? → A: Plain data only in v1 (dict / str / bytes / file path in; dict / text out); no FHIR model-library integration or extra.
- Q: Which open-source licence should `fvs_client` be released under? → A: Apache-2.0.
- Q: Should result/response objects be Pydantic models or standard-library dataclasses? → A: Standard-library frozen dataclasses with an internal parser (no extra runtime dependency), plus an option to get the raw, unparsed result instead.
- Q: Should the first PyPI release be a 0.x pre-release or a stable 1.0.0? → A: Start at 0.1.0; promote to 1.0.0 after real-world feedback. Breaking changes in 0.x are allowed but MUST be listed in the changelog.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Validate a FHIR resource (Priority: P1)

A Python developer building a healthcare application installs the SDK, points it at an FVS deployment with an API key, and validates a FHIR resource (given as a Python dictionary, a JSON string, an XML string, or a file) for a chosen FHIR version. Optionally they name an IG package, extra profiles, or a terminology setting for that one request. They get back a result object that tells them clearly whether the resource is valid, lists each issue with its severity, location and message, and tells them which validator context, IG version and terminology setting the service actually used.

**Why this priority**: Validation is the reason the service exists and the most frequent call. On its own it is a usable MVP.

**Independent Test**: Against a running FVS (or a recorded/mocked one), validate a known-valid and a known-invalid Patient resource for R4 with and without an IG, and check that the result objects report validity, issues and the context used correctly.

**Acceptance Scenarios**:

1. **Given** a configured client and a valid R4 Patient as a dictionary, **When** the developer validates it for R4 with no IG, **Then** the result reports valid, has no error-level issues, and reports the context used as the core specification (`base`).
2. **Given** an invalid resource, **When** it is validated, **Then** the result reports not valid and lists every issue with severity (fatal, error, warning, information), location and message. No exception is raised, because the validation itself completed.
3. **Given** an IG named as `name#version`, `name#latest` or a bare `name`, **When** the developer validates against it, **Then** the SDK encodes the IG reference correctly (including the `#` and `|` characters) and the result reports the concrete IG version used.
4. **Given** the developer asks for the result as a FHIR OperationOutcome (JSON or XML), **When** validation completes, **Then** the SDK returns the OperationOutcome in the requested format.
5. **Given** the developer asks for the raw result, **When** validation completes, **Then** the SDK returns the unparsed response (status, headers, body) instead of a result object; and **Given** a parsed result, **When** the developer inspects it, **Then** the original response body is still available on it and it can be exported as a plain dictionary.
6. **Given** one or more extra profile URLs and/or a terminology server and mode for this request, **When** the developer validates, **Then** the SDK sends them and the result reports the terminology mode, server and source the service used.
7. **Given** an XML resource, **When** the developer validates it, **Then** the SDK sends it with the correct XML content type and returns the same kind of result as for JSON.

---

### User Story 2 - Handle service errors and limits predictably (Priority: P1)

When something goes wrong (bad API key, forbidden operation, unknown IG package, unknown profile, rate limit hit, service not ready or overloaded, network failure, timeout), the developer gets a specific, typed error that carries the service's problem details (type, title, status, detail, correlation/request id, and type-specific fields such as unresolved profiles or retry-after seconds). They can catch broad or narrow error categories and decide how to react.

**Why this priority**: A validation SDK that hides or flattens errors is unusable in production pipelines. This is needed alongside Story 1 for a real MVP.

**Independent Test**: Use a mocked service that returns each documented error status and problem type; check that the SDK raises the matching error category with every problem field intact.

**Acceptance Scenarios**:

1. **Given** a missing, unknown or expired API key, **When** any protected call is made, **Then** the SDK raises an authentication error carrying the request id.
2. **Given** a validation request naming profiles the service cannot resolve, **When** the call returns, **Then** the SDK raises an unknown-profile error that lists the unresolved profile URLs.
3. **Given** the service answers 429 rate-limited with a retry delay, **When** automatic retry is off, **Then** the SDK raises a rate-limit error exposing the retry-after seconds, the scope (key or organisation) and the limit.
4. **Given** automatic retry is on, **When** the service answers 429 or 503 (not-ready, overloaded), **Then** the SDK waits for the service-advised delay (or a bounded backoff when none is given) and retries, up to the configured maximum, before raising.
5. **Given** the service is unreachable or does not answer within the configured timeout, **When** a call is made, **Then** the SDK raises a connection or timeout error that is distinct from service-reported errors.
6. **Given** any successful or failed response, **When** the developer inspects the result or error, **Then** the service's request id and any rate-limit information (limit, remaining, reset) are available.

---

### User Story 3 - Use the SDK in asynchronous applications (Priority: P2)

A developer writing an asynchronous service (for example a web API or a batch pipeline that validates many resources at once) uses an asynchronous client that offers the same operations, options, results and errors as the synchronous client, and can validate many resources concurrently.

**Why this priority**: Many modern Python health-data services are asynchronous, and batch validation benefits from concurrency. The synchronous client alone is already a viable MVP.

**Independent Test**: Run the same scenario suite used for Stories 1 and 2 against the asynchronous client and check for identical outcomes; validate a batch of resources concurrently and check every result.

**Acceptance Scenarios**:

1. **Given** an asynchronous client, **When** the developer validates a resource, **Then** the result is identical in shape and content to the synchronous client's result.
2. **Given** 100 resources, **When** the developer validates them concurrently with a concurrency limit they choose, **Then** every resource gets its own result or error, in a way that maps back to its input.
3. **Given** either client, **When** the developer uses it as a context manager, **Then** its network resources are released on exit.

---

### User Story 4 - Manage IG packages and validator contexts (Priority: P2)

An administrator (holding an ADMIN key) uses the SDK to automate the IG lifecycle: upload a package archive or register one from a registry or URL (optionally with dependencies), read a package's declared dependencies, include a stored IG version (or a pair of IGs) as a validator context for a FHIR version with a sharing and terminology setting, change a context's or package's sharing, ownership or terminology, and exclude a context.

**Why this priority**: Needed to operate the service from scripts and CI, but used far less often than validation and only by administrators.

**Independent Test**: Against a running FVS with an ADMIN key: register a public IG, include it for R4, validate against it, change its sharing, then exclude it; check each step's response object.

**Acceptance Scenarios**:

1. **Given** an ADMIN key and a local `.tgz` IG archive, **When** the administrator uploads it with a sharing choice, **Then** the SDK returns the stored package's name, version, owner, sharing and any warnings.
2. **Given** an IG name and a version (exact, `latest`, or a series like `1.2.x`), **When** the administrator registers it, **Then** the SDK returns the concrete version, the requested version, whether it was downloaded, owner, sharing and warnings.
3. **Given** a stored IG version, **When** the administrator includes it for a FHIR version (one IG or two IGs, with optional sharing and terminology), **Then** the SDK returns the context key, aliases, resolved IG versions, terminology, owner, sharing and warnings.
4. **Given** an included context, **When** the administrator changes its sharing, ownership or terminology, or excludes it, **Then** the SDK returns the service's confirmation, including any warnings.
5. **Given** a VALIDATE-only key, **When** an administrative operation is attempted, **Then** the SDK raises a permission error.
6. **Given** a stored IG version, **When** a user asks for its dependencies, **Then** the SDK returns the package name, version and list of declared dependencies.

---

### User Story 5 - Check service health (Priority: P3)

An operator or a deployment script uses the SDK to check whether an FVS deployment is live, ready to serve, and healthy, including which FHIR versions are enabled, whether access control is on, and the reasons when it is not ready.

**Why this priority**: Useful for readiness gates and diagnostics, but simple and not on the main path.

**Independent Test**: Call liveness, readiness and health on a running and on a not-ready deployment (mocked); check that status, reasons and enabled versions are reported.

**Acceptance Scenarios**:

1. **Given** a ready deployment, **When** readiness is checked, **Then** the SDK reports ready with the per-version information.
2. **Given** a deployment that is not ready (service answers 503 with reasons), **When** readiness or health is checked, **Then** the SDK returns a not-ready report with the reasons rather than raising.
3. **Given** a deployment, **When** health is checked, **Then** the SDK reports database status, served FHIR versions, terminology registry source and whether access control is enabled.

---

### User Story 6 - Install and adopt the SDK easily (Priority: P1)

A developer installs the SDK from PyPI with one standard command, gets full editor auto-completion and type checking, finds a quick-start guide and reference documentation, and can trust that each release follows semantic versioning with a changelog.

**Why this priority**: The user's base principles require modern publishing practice; without a clean, trustworthy package, no other story reaches users.

**Independent Test**: In a fresh environment with the minimum supported Python version, install the published package, run the quick-start example against a test service, and run a static type checker on code that uses the SDK.

**Acceptance Scenarios**:

1. **Given** a clean environment with a supported Python version, **When** the developer installs `fvs_client` from PyPI, **Then** installation succeeds and pulls in only the SDK's declared runtime dependencies.
2. **Given** an environment with a Python version older than the minimum, **When** installation is attempted, **Then** the installer refuses it with a clear version requirement.
3. **Given** code that uses the SDK, **When** a static type checker runs on it, **Then** the SDK's public interface is fully typed and the checker reports no missing-type issues.
4. **Given** a new release, **When** a developer reads the changelog, **Then** they can see what changed and whether it breaks compatibility.

---

### Edge Cases

- An IG reference containing `#` or `|` must reach the service intact (correctly URL-encoded); a raw `#` would otherwise silently drop the version.
- An empty body, a body that is not FHIR, or an unparseable string: the service answers invalid-resource; the SDK must surface it as a typed request error, not a crash.
- A FHIR version string in a different case (`r4`, `Stu3`) or an unsupported value (`R6`, `DSTU2`): the SDK accepts the four supported versions case-insensitively and rejects unsupported values before sending anything.
- More than 10 profiles, or a profile URL longer than 1024 characters, or a terminology server address longer than 512 characters: the SDK rejects them locally with a clear message, matching the service's documented limits.
- `txMode=none` combined with a terminology server: the SDK rejects the combination locally.
- A validation result with a regex-timeout issue is still a successful (valid or invalid) result, not an error.
- Terminology that could not be checked is reported by the service as a warning; the SDK must not turn it into an error.
- A 404 for a package the caller may not see is indistinguishable from "not stored"; the SDK must not claim more than the service says.
- 424 dependency-not-found, 409 conflict/alias-conflict, 413 package-too-large/payload-too-large, 422 fhir-version-disabled/package-unsafe, 400 dependency-conflict (with its `conflicts` list), 400 unsupported-fhir-version (a version this deployment does not serve), 405, 406 and 415 must each map to a recognisable error.
- A problem `type` arrives as a full URI; matching on it must work by short name regardless of the URI's host or prefix.
- 503 `tx-registry-unavailable` may arrive without a Retry-After; retry (when enabled) then uses the bounded backoff.
- An error response whose body is not a problem document (for example from a proxy or load balancer): the SDK still raises a typed HTTP error with the status code and raw text.
- A response field the SDK does not know (newer service version): the SDK ignores it without failing and keeps it available to the developer.
- Access control disabled on the deployment (no API key needed): the SDK works without a key.
- Very large IG archives on upload: the SDK streams the file rather than loading it fully into memory, and surfaces 413 when the service refuses the size. Body and upload size limits are operator-configured on the service (defaults 20 MB per request body, 50 MB per compressed IG upload), so the SDK MUST NOT enforce them locally.
- The API key must never appear in logs, error messages or string representations of the client.

## Requirements *(mandatory)*

### Functional Requirements

**Client configuration**

- **FR-001**: The SDK MUST let a developer create a client from a service base URL and an optional API key, and MUST also read these from environment variables (`FVS_BASE_URL`, `FVS_API_KEY`) when not given explicitly.
- **FR-002**: The SDK MUST let the developer configure request timeout, automatic retry (on/off, maximum attempts), extra default headers and a custom user agent suffix, with documented defaults.
- **FR-003**: The SDK MUST send the API key as a bearer credential on every request when one is configured, and MUST never include the key in logs, error messages or object string representations.
- **FR-004**: The SDK MUST provide both a synchronous and an asynchronous client exposing the same operations, parameters, results and errors.
- **FR-005**: Both clients MUST support use as a context manager and an explicit close, releasing network connections, and MUST allow the developer to supply their own pre-configured HTTP transport/session (for proxies, custom TLS, testing).

**Validation**

- **FR-006**: The SDK MUST validate a single resource for a FHIR version (STU3, R4, R4B, R5, case-insensitive), accepting the resource as a dictionary, a JSON string or bytes, an XML string or bytes, or a file path, and MUST send the matching content type.
- **FR-007**: The SDK MUST support the optional validation inputs: one IG reference (`name`, `name#version`, `name#latest`) or a two-IG reference (`name#version|name#version`), a list of extra profile URLs, a terminology server, and a terminology mode (`none`, `server`, `ecosystem`), and MUST encode them as the service requires.
- **FR-008**: The SDK MUST check documented input limits locally before sending (supported FHIR version, at most 10 distinct profiles, profile URL ≤ 1024 characters, IG reference ≤ 256 characters, terminology server ≤ 512 characters and an http(s) base URL, no terminology server with mode `none`) and raise a clear local validation error when they are broken.
- **FR-009**: The SDK MUST return, by default, a structured validation result with: valid flag, list of issues (severity, location, message), FHIR version, applied profiles, IG package used, its owner and sharing, plus the response metadata: validator context used, context owner and sharing, terminology mode, server and source, request id and rate-limit information.
- **FR-010**: The SDK MUST let the developer request the result as a FHIR OperationOutcome in JSON (as a dictionary) or XML (as text), with the same response metadata available.
- **FR-011**: The validation result MUST offer convenience access to issues filtered by severity (for example only errors and fatals) and a simple way to tell whether any error-level issue exists.
- **FR-012**: The SDK MUST provide a helper to validate many resources concurrently with a developer-chosen concurrency limit, returning one result or one error per input in input order, without one failure stopping the rest. Every SDK error (including local input errors) is captured in its slot; only unexpected programming errors (non-SDK exceptions) propagate, so they're not hidden.

**Validator contexts and IG packages**

- **FR-013**: The SDK MUST support including a validator context for a FHIR version from one IG (id plus optional version: exact, `latest`, or a series) or two IGs, with optional sharing and terminology settings, and MUST return the full include response.
- **FR-014**: The SDK MUST support excluding a validator context (single IG `name#version` or two-IG key) and changing a context's sharing, owner or terminology, returning the full service response including warnings.
- **FR-015**: The SDK MUST support uploading an IG package archive from a file path or an open binary file with a sharing choice, streaming the content, and returning the stored-package response.
- **FR-016**: The SDK MUST support registering an IG package by name and version (exact, `latest`, or series) or by download URL, with dependency and sharing options, returning the registration response.
- **FR-017**: The SDK MUST support changing a stored IG package's sharing or owner, and reading a stored IG package's declared dependencies.
- **FR-018**: The SDK MUST NOT expose the service's deprecated package-file-listing operation as a primary feature; if offered, it MUST be clearly marked deprecated.

**Health**

- **FR-019**: The SDK MUST provide health, liveness and readiness checks that return structured reports, and MUST return (not raise) a not-ready/unhealthy report when the service answers 503 with a report body. These checks need no API key and MUST work on a client created without one.

**Errors and retries**

- **FR-020**: The SDK MUST raise errors from a single SDK base error type, with distinct categories at least for: local input errors, connection errors, timeouts, authentication (401), permission (403), not found (404), conflict (409), request/validation problems (400, 405, 406, 413, 415, 422, 424), rate limiting (429), service unavailable (503) and server errors (5xx).
- **FR-021**: Every service-reported error MUST carry the problem document fields (type, title, status, detail, correlation id, issues, unresolved profiles, conflicts, scope, limit, retry-after) when present, plus the HTTP status, request id and raw body; problem types MUST be inspectable as values so callers can branch on them (for example `unknown-profile`, `package-not-found`, `tx-server-not-registered`).
- **FR-021a**: The service sends the problem `type` as a URI (e.g. `https://nazrulworld.github.io/fhir-validation-service/problems/rate-limited`). The SDK MUST expose both the full `type` URI and its short name (the last path segment, e.g. `rate-limited`), and MUST provide a catalogue of every problem type the service documents: `invalid-request`, `invalid-resource`, `dependency-conflict`, `unknown-profile`, `unsupported-fhir-version`, `package-source-not-allowed`, `tx-server-not-registered` (400); `unauthorized` (401); `forbidden` (403); `not-found`, `package-not-found` (404); `method-not-allowed` (405); `not-acceptable` (406); `conflict`, `alias-conflict` (409); `package-too-large`, `payload-too-large` (413); `unsupported-media-type` (415); `package-unsafe`, `fhir-version-disabled` (422); `rate-limited` (429); `dependency-not-found` (424); `internal-error` (500); `not-ready`, `overloaded`, `tx-registry-unavailable`, `insufficient-capacity` (503). A problem type not in the catalogue MUST still be raised by its HTTP status category with its type preserved.
- **FR-022**: When automatic retry is enabled, the SDK MUST retry only 429 and 503 responses and connection failures, honouring the service's Retry-After when given and a bounded exponential backoff otherwise, up to the configured maximum attempts. If the service-advised wait is longer than a configurable maximum (default 60 seconds), the SDK MUST raise the error at once instead of waiting. It MUST NOT retry any other error status. For administrative operations (which change state), retry MUST be off by default and, when turned on, MUST apply only to 429 and 503 responses (where the service did not perform the change), never to connection failures or timeouts.
- **FR-023**: The SDK MUST tolerate unknown fields in service responses without failing and keep them accessible.

**Result objects and raw results**

- **FR-029**: All parsed results (validation results, issues, include/exclude/registration/upload/access responses, dependency lists, health/readiness reports, problem details) MUST be immutable, fully typed objects built only with the standard library (no third-party modelling dependency), and MUST offer a method to export themselves as a plain dictionary.
- **FR-030**: Every parsed result MUST keep the original response body exactly as received (decoded JSON dictionary, or text for XML) so callers can read fields the SDK does not model.
- **FR-031**: Every operation on both clients MUST accept an option to return the raw result instead of a parsed object: a raw response exposing the HTTP status code, all response headers, the body as bytes and text, the body decoded from JSON when it is JSON, and the request id and rate-limit information. In raw mode, success responses MUST NOT be parsed into result objects; error statuses MUST still raise the same typed SDK errors (which themselves carry the raw response).

**Quality and distribution**

- **FR-024**: The SDK MUST be published to PyPI under the name `fvs_client`, MUST declare Python 3.11 as the minimum version, MUST ship type information for its whole public interface, and MUST be licensed Apache-2.0 (declared in package metadata, with the licence text included in every distribution).
- **FR-025**: The SDK MUST perform all communication with the service through `httpx` and MUST keep its required runtime dependencies to a minimum, each declared with a compatible version range.
- **FR-026**: The SDK MUST follow semantic versioning, keep a changelog, and document which FVS API version(s) each release supports. The first release MUST be 0.1.0; while in 0.x, breaking changes are allowed but MUST be flagged as breaking in the changelog. The SDK version is independent of the service API version.
- **FR-027**: The SDK MUST provide user documentation: installation, quick start, a guide per operation group, error handling, async usage, and an API reference.
- **FR-028**: The SDK MUST emit diagnostic logs (method, path, status, duration, request id; never the API key or resource content) through the standard logging facility, silent by default.

### Key Entities

- **Client (sync and async)**: The developer's entry point; holds base URL, credentials, timeouts, retry policy and the connection pool; groups operations into validation, validator contexts, IG packages and health.
- **FHIR Version**: One of STU3, R4, R4B, R5.
- **IG Reference**: Identifies the IG(s) a request is about: name, optional version (exact, `latest`, or series), or a pair of exact name#version values.
- **Validation Options**: IG reference, extra profiles, terminology server, terminology mode, and desired result format.
- **Validation Result**: Valid flag, issues, FHIR version, applied profiles, IG package/owner/sharing, and response metadata.
- **Validation Issue**: Severity (fatal, error, warning, information), location, message.
- **Response Metadata**: Request id, validator context key/owner/sharing, terminology mode/server/source, rate-limit limit/remaining/reset.
- **Raw Response**: The unparsed service response returned when the caller asks for raw results: HTTP status, all headers, body as bytes/text/decoded JSON, plus request id and rate-limit information. Errors carry one too.
- **Terminology Settings**: Mode (none, server, ecosystem) and optional server address.
- **Validator Context**: A pre-built validator for one or two IG versions under a FHIR version, with key, aliases, owner, sharing and terminology.
- **IG Package**: A stored package (name, version) with owner, sharing and declared dependencies.
- **Problem / SDK Error**: A service-reported error (problem type, title, status, detail, correlation id and type-specific fields) or a local/transport failure.
- **Health / Readiness Report**: Status, timestamp, reasons, per-version readiness, database status, served FHIR versions, terminology source, access-control state.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: A developer new to the SDK can install it and validate their first resource against a running service in under 5 minutes by following the quick start.
- **SC-002**: 100% of the operations in the service's published contract (except the deprecated file listing and the metrics scrape) can be performed through the SDK without writing raw HTTP requests.
- **SC-003**: 100% of the documented error statuses and problem types are surfaced as a recognisable SDK error category in automated tests.
- **SC-004**: The SDK adds less than 5 milliseconds of its own processing time per validation call for a typical resource (under 100 KB), measured against a local mock service.
- **SC-005**: Concurrent validation of 1,000 resources completes with every input accounted for (one result or one error each) and no leaked connections.
- **SC-006**: Automated tests cover at least 90% of the SDK's code and run on every supported Python version (3.11 and every newer stable version) on Linux, macOS and Windows.
- **SC-007**: The public interface passes strict static type checking with zero errors, and every public function and type has reference documentation.
- **SC-008**: Every release is built, tested and published automatically from a tagged version, with a changelog entry, and the published package installs cleanly in a fresh environment.
- **SC-009**: No test, log line, error message or object representation exposes the configured API key.

## Assumptions

- **User-given constraints** (these are design decisions the user has already made, recorded here so planning respects them): PyPI distribution name is `fvs_client`; minimum Python version is 3.11; all HTTP communication uses `httpx`; the project follows current best practice for Python packaging and publishing.
- The SDK targets the FVS published contract version 1.0.0 (OpenAPI 3.0.3, `src/main/resources/openapi.yaml` in the upstream repository: https://raw.githubusercontent.com/nazrulworld/fhir-validation-service/refs/heads/main/src/main/resources/openapi.yaml), with the upstream wiki (https://github.com/nazrulworld/fhir-validation-service/wiki: API Documentation, API Throttling and Rate Limits) as the companion reference for problem types, auth and client retry guidance. Where they differ, the OpenAPI contract wins and the difference is noted in planning. Newer service versions are expected to stay backward compatible; unknown fields are tolerated.
- Target users are Python developers integrating validation into applications, pipelines and CI, plus administrators automating IG management. A command-line tool is out of scope for v1 (confirmed); it will be specified as a separate later feature built on this library, and v1 MUST NOT register any console entry point.
- The Prometheus metrics endpoint is meant for monitoring systems, not application code, and is out of scope.
- The SDK validates one resource per service call; the service has no batch endpoint, so "batch" validation is client-side concurrency over single calls.
- The SDK does not parse or model FHIR resources itself; it accepts and returns plain data (dictionaries / text). Integration with third-party FHIR model libraries (including `fhir.resources`), whether built in or as an optional extra, is out of scope for v1 (confirmed).
- The SDK does not manage API keys, organisations or rate-limit configuration; those are service-side operator tasks.
- Automatic retry is off by default for administrative operations and on by default (with a small maximum) for validation and health calls; both are configurable.
- Default request timeout is generous enough for validation with terminology checks (for example 60 seconds total), and configurable per client and per call.
- The project is released under the Apache License 2.0 (confirmed).
- Integration tests against a real service can use the upstream project's container image; unit tests use a mocked HTTP layer and need no running service.
