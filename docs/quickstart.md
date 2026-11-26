# Quick start

## 1. Run a FHIR Validation Service

See the service's [Installation Guide](https://github.com/nazrulworld/fhir-validation-service/wiki/Installation-Guide).
For a local service:

```bash
git clone --depth 1 --branch v1.0.0 https://github.com/nazrulworld/fhir-validation-service.git
cd fhir-validation-service && cp .env.example .env   # set the passwords and API keys
FV_TAG=1.0.0 docker compose up -d --wait
```

## 2. Validate a resource

```python
from fvs_client import Client

with Client("http://127.0.0.1:8880", api_key="<FV_VALIDATOR_API_KEY>") as fvs:
    ok = fvs.validate({"resourceType": "Patient", "active": True}, fhir_version="R4")
    print(ok.valid, ok.context.key, [i.severity for i in ok.issues])
    # True base [<Severity.WARNING: 'WARNING'>]   (dom-6: no narrative)

    bad = fvs.validate(
        {"resourceType": "Patient", "gender": "unknown-value", "birthDate": "2020-13-45"},
        fhir_version="r4",
    )
    print(bad.valid, len(bad.errors), bad.meta.request_id)
```

## 3. Next steps

- [Validation](validation.md): IGs, profiles, terminology, result formats, files
- [Errors & retries](errors-and-retries.md)
