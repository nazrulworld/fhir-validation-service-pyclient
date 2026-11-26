# Quickstart & Validation Guide: `fvs_client`

How to prove the feature works end to end. API details are in
[contracts/public-api.md](./contracts/public-api.md); types are in
[data-model.md](./data-model.md).

## Prerequisites

- Python 3.11 or newer and [uv](https://docs.astral.sh/uv/) 0.13 or newer
- For scenarios 2–7, Docker with Compose v2 and about 4 GB free RAM for the service container

## 1. Static and unit gates (no service needed)

```bash
uv sync --all-groups
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict src tests
uv run pyright
uv run pytest -m "not integration" --cov --cov-branch --cov-fail-under=90
```

**Expected**: every command exits 0. Unit and contract tests cover:
- every row of [contracts/http-mapping.md](./contracts/http-mapping.md)
- every problem type
- the retry tables
- the local pre-flight checks
- sync/async parity

## 2. Start a local FHIR Validation Service 1.0.0

Use the upstream Compose setup (postgres plus one validator on `127.0.0.1:8880`):

```bash
git clone --depth 1 --branch v1.0.0 https://github.com/nazrulworld/fhir-validation-service.git /tmp/fvs
cd /tmp/fvs && cp .env.example .env
# edit .env: set PG_PASSWORD = FV_PG_PASSWORD, FV_ADMIN_API_KEY, FV_VALIDATOR_API_KEY (long random values)
FV_TAG=1.0.0 docker compose up -d --wait
curl -fsS http://127.0.0.1:8880/health/readiness
```

**Expected**: readiness returns `{"status":"UP",…}`. The first start can take about 2 minutes.

```bash
export FVS_BASE_URL=http://127.0.0.1:8880
export FVS_API_KEY=<FV_VALIDATOR_API_KEY>   # validation key
export FVS_ADMIN_API_KEY=<FV_ADMIN_API_KEY> # used by admin scenarios / integration tests
```

## 3. Story 6: install from a built wheel in a clean environment

```bash
uv build
uv venv /tmp/fvs-smoke --python 3.11 && uv pip install --python /tmp/fvs-smoke dist/fvs_client-*.whl
/tmp/fvs-smoke/bin/python -c "import fvs_client; print(fvs_client.__version__, fvs_client.SUPPORTED_API)"
```

**Expected**: the version is printed, and the only dependencies installed are `httpx`, `anyio`
and their own dependencies. Installing into a Python 3.10 environment is refused because of
`requires-python`.

## 4. Story 1: validate a resource (the "first validation in under 5 minutes" check, SC-001)

```python
from fvs_client import Client

with Client() as fvs:  # reads FVS_BASE_URL / FVS_API_KEY
    ok = fvs.validate({"resourceType": "Patient", "active": True}, fhir_version="R4")
    bad = fvs.validate(
        {"resourceType": "Patient", "gender": "unknown-value", "birthDate": "2020-13-45"},
        fhir_version="r4",
    )
    print(ok.valid, ok.context.key, [i.severity for i in ok.issues])
    print(bad.valid, len(bad.errors), bad.meta.request_id)
```

**Expected**:
- `True base ['WARNING']` (the dom-6 narrative warning)
- `False` with at least 2 errors and a request id
- No exception for the invalid resource

Also check:
- `result_format=ResultFormat.OPERATION_OUTCOME_JSON` returns a dict with
  `resourceType == "OperationOutcome"`
- `raw=True` returns a `RawResponse` with `status_code == 200`
- An XML string resource validates the same way

## 5. Story 2: errors and limits

| Action | Expected |
|--------|----------|
| `Client(api_key="wrong").validate(..., fhir_version="R4")` | `AuthenticationError`, `status_code == 401`, `request_id` set |
| `validate(..., profiles=["http://example.org/nope"])` | `UnknownProfileError` with `unresolved_profiles == ("http://example.org/nope",)` |
| `validate(..., ig="no.such.ig#1.0.0")` | `NotFoundError`, `problem_type == ProblemType.PACKAGE_NOT_FOUND` |
| `validate(..., fhir_version="R6")` | `InputError`, raised before any HTTP request |
| `validate(..., profiles=[f"http://p/{i}" for i in range(11)])` | `InputError` |
| `Client(base_url="http://127.0.0.1:1").health.liveness()` | `FVSConnectionError` after the retries |
| `repr(Client(api_key="secret"))` and all captured logs | never contain `secret` (SC-009) |

## 6. Story 4: admin lifecycle (needs `FVS_ADMIN_API_KEY` and outbound access to packages.fhir.org)

```python
import os
from fvs_client import Client, IgRef, AccessChange

with Client(api_key=os.environ["FVS_ADMIN_API_KEY"]) as admin:
    reg = admin.packages.register("hl7.fhir.uv.ips", "1.1.0")
    deps = admin.packages.dependencies(reg.name, reg.version)
    inc = admin.contexts.include("R4", IgRef(reg.name, reg.version))
    upd = admin.contexts.update("R4", inc.key, AccessChange(shareable=True))
    exc = admin.contexts.exclude("R4", inc.key)
```

**Expected**:
- Each call returns its model.
- `inc.key == "hl7.fhir.uv.ips#1.1.0"`.
- Validating with `ig=inc.key` between `include` and `exclude` gives
  `result.context.key == inc.key`.
- After `exclude`, the same validation raises `BadRequestError` (`invalid-request`).
- The same admin calls made with the validation key raise `PermissionDeniedError`.

## 7. Stories 3 and 5: async, batch and health

```python
import anyio
from fvs_client import AsyncClient


async def main() -> None:
    async with AsyncClient() as fvs:
        results = await fvs.validate_many(
            [{"resourceType": "Patient"}] * 20 + ["not fhir"], fhir_version="R4", concurrency=10
        )
        assert len(results) == 21 and isinstance(results[-1], Exception)
        ready = await fvs.health.readiness()
        print(ready.is_ready, (await fvs.health.check()).served_fhir_versions)


anyio.run(main)
```

**Expected**:
- 20 results plus 1 `InputError`, in input order.
- The batch stays under FVS's default per-key limit of 30 validation requests per minute. A
  larger burst still returns one entry per input, but the entries over the limit are
  `RateLimitError` once the retries are used up. (Live run: 101 inputs gave 79 results,
  21 `RateLimitError` and 1 `InputError`.)
- Readiness is `True`, and the served versions are listed.
- A not-ready service (503 with a readiness body) is covered by unit tests with mocked
  responses: the call returns a report with `is_ready == False` and its reasons, and does not
  raise. To see it live, call `readiness()` right after `docker compose restart validator`,
  while the service is starting.

## 8. Integration suite and teardown

```bash
FVS_IT_BASE_URL=$FVS_BASE_URL FVS_IT_API_KEY=$FVS_API_KEY FVS_IT_ADMIN_API_KEY=$FVS_ADMIN_API_KEY \
  uv run pytest -m integration
cd /tmp/fvs && docker compose down -v
```

**Expected**: all integration tests pass, and the same suite passes for `Client` and
`AsyncClient`.

## Validation log

**2026-11-26 (implementation run, macOS, uv 0.13):**

| Section | Result |
|---------|--------|
| §1 Static and unit gates | ✅ ruff, ruff format, mypy (strict), pyright (strict on `src/`) clean; 694 tests pass, 96.5% branch coverage, on CPython 3.11, 3.14 and 3.15; also passes on the trio backend |
| §3 Clean install from the wheel | ✅ `uv build`, `twine check --strict` and `scripts/check_dist.py` pass (requires-python `>=3.11`, Apache-2.0, deps only httpx + anyio) |
| SC-004 overhead (`pytest -m perf`) | ✅ median 0.68 ms, p95 0.75 ms per `validate()` of a ~90 KB resource (budget 5 ms) |
| §2, §4–§8 against a live FVS 1.0.0 | ✅ see the run below |

**2026-11-26 (live run, FVS `ghcr.io/nazrulworld/fhir-validation-service:1.0.0` via Docker Compose, CPython 3.14):**

| Section | Result |
|---------|--------|
| §2 Start the service | ✅ healthy, readiness `UP`. Run under `COMPOSE_PROJECT_NAME=fvsclient-it`, because an existing `fhir_pgdata` volume (different password) made the default project fail with `password authentication failed` |
| §4 Validate | ✅ valid Patient → `True base ['warning']`; invalid Patient → `False`, ≥ 2 errors, request id set; OperationOutcome JSON, `raw=True` and XML input all as expected |
| §5 Errors and limits | ✅ every row as expected (401 `AuthenticationError` with request id, `UnknownProfileError.unresolved_profiles`, `package-not-found`, local `InputError`s, `FVSConnectionError`, key absent from `repr` and DEBUG logs) |
| §6 Admin lifecycle | ✅ register → dependencies → include (`hl7.fhir.uv.ips#1.1.0`) → validate in that context → update → exclude → validate raises `BadRequestError`; the validation key gets `PermissionDeniedError` |
| §7 Async, batch, health | ✅ 20 results plus 1 `InputError` in order; readiness `True`; served versions STU3, R4, R4B, R5. The original 101-item batch hit the default limit of 30 validations per minute per key (79 results, 21 `RateLimitError`, 1 `InputError`), so the example now uses 20 items |
| §8 Integration suite | ✅ 14 passed (asyncio and default backends) |

**Findings:**

- **R13 confirmed**: FVS splits `profile` on both a literal `,` and `%2C`. Two core profiles in one call are both applied.
- **Upstream difference**: FVS 1.0.0 answers `400 unknown-profile` for a core-spec profile given as `url|version` (for example `http://hl7.org/fhir/StructureDefinition/Patient|4.0.1`, even alone), although the OpenAPI `profile` description says `url|version` is matched. The SDK passes the value through unchanged. The integration test now uses two distinct core URLs. This is worth reporting upstream.
