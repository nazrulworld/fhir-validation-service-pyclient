# fvs_client

[![PyPI](https://img.shields.io/pypi/v/fvs_client.svg)](https://pypi.org/project/fvs_client/)
[![Python versions](https://img.shields.io/pypi/pyversions/fvs_client.svg)](https://pypi.org/project/fvs_client/)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)
[![CI](https://github.com/nazrulworld/fhir-validation-service-pyclient/actions/workflows/ci.yml/badge.svg)](https://github.com/nazrulworld/fhir-validation-service-pyclient/actions/workflows/ci.yml)

Typed Python SDK, sync and async, for the
[FHIR Validation Service](https://github.com/nazrulworld/fhir-validation-service) (FVS): an HTTP
service that validates FHIR resources (STU3, R4, R4B, R5) against the core specification and
Implementation Guide packages. Read the service's
[wiki](https://github.com/nazrulworld/fhir-validation-service/wiki) for deployment and API details.

- Validate a resource (dict, JSON/XML text, or a file streamed from disk), optionally against an
  IG, extra profiles and a per-request terminology setting
- Typed, immutable results; FHIR `OperationOutcome` (JSON/XML) or the raw response on request
- One exception per failure kind, carrying the service's RFC 9457 problem details and request id
- Bounded retries that honour `Retry-After` for 429/503
- Administer IG packages and validator contexts; check health and readiness
- Same API for `Client` and `AsyncClient`; only dependencies are `httpx` and `anyio`

## Installation

```bash
pip install fvs_client
# or
uv add fvs_client
```

Requires Python 3.11 or newer (tested on 3.11–3.15).

## Quick start

```python
from fvs_client import Client

with Client("http://127.0.0.1:8880", api_key="…") as fvs:
    ok = fvs.validate({"resourceType": "Patient", "active": True}, fhir_version="R4")
    bad = fvs.validate(
        {"resourceType": "Patient", "gender": "unknown-value", "birthDate": "2020-13-45"},
        fhir_version="r4",
    )
    print(ok.valid, ok.context.key)  # True base
    print(bad.valid, [i.message for i in bad.errors])
```

An invalid resource is a **result** (`valid=False`), not an exception.

### Configuration

| Argument | Environment variable | Default |
|----------|----------------------|---------|
| `base_url` | `FVS_BASE_URL` | required |
| `api_key` | `FVS_API_KEY` | none (health checks and public-mode deployments need no key) |
| `timeout` | | 60 s (10 s to connect); `None` is not allowed |
| `retries` | | 2 retries for safe operations, 0 for administrative ones |

Pass `http_client=httpx.Client(...)` to use your own proxies, TLS settings or transport.

### Errors

```python
from fvs_client import APIError, Client, RateLimitError, UnknownProfileError

with Client() as fvs:  # FVS_BASE_URL / FVS_API_KEY
    try:
        fvs.validate(resource, fhir_version="R4", profiles=["http://example.org/P"])
    except UnknownProfileError as e:
        print("unknown profiles:", e.unresolved_profiles)
    except RateLimitError as e:
        print(f"slow down: retry in {e.retry_after}s ({e.scope} limit {e.limit}/min)")
    except APIError as e:
        print(e.status_code, e.problem_type, e.request_id)
```

## Compatibility and stability

- Supported service API: **FHIR Validation Service 1.0.x** (`fvs_client.SUPPORTED_API`).
- The SDK follows [Semantic Versioning](https://semver.org/). While it is **0.x**, breaking
  changes can happen in minor releases and are flagged **BREAKING** in the
  [changelog](CHANGELOG.md).

## Documentation

Full guides and the API reference: <https://nazrulworld.github.io/fhir-validation-service-pyclient/>.

## License

[Apache License 2.0](LICENSE). FHIR® and HL7® are registered trademarks of Health Level Seven
International; this project is not affiliated with HL7.
