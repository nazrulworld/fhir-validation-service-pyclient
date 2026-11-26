# fvs_client

Typed Python SDK, sync and async, for the
[FHIR Validation Service](https://github.com/nazrulworld/fhir-validation-service) (FVS).

```python
from fvs_client import Client

with Client("http://127.0.0.1:8880", api_key="…") as fvs:
    result = fvs.validate({"resourceType": "Patient"}, fhir_version="R4")
    print(result.valid, [i.message for i in result.errors])
```

- **Supported service API:** FHIR Validation Service 1.0.x (`fvs_client.SUPPORTED_API`)
- **Python:** 3.11 or newer
- **Runtime dependencies:** `httpx`, `anyio`
- **License:** Apache-2.0

Start with [Installation](installation.md) and the [Quick start](quickstart.md).
