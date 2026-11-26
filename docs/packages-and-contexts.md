# IG packages & validator contexts

Validation against an Implementation Guide needs two things on the service:

1. the IG **package** is *stored* (uploaded, or registered from the package registry);
2. a **validator context** for it is *included* for the FHIR version (pre-built on every instance).

These are administrative operations: they need an **ADMIN** API key (and, if the operator set an
admin network allowlist, a call from an allowed network). A VALIDATE key gets
`PermissionDeniedError`.

```python
from fvs_client import AccessChange, Client, IgRef, TerminologySettings

with Client("https://fvs.example.org", api_key="<ADMIN key>") as admin:
    reg = admin.packages.register("hl7.fhir.uv.ips", "1.1.x")  # → concrete version
    deps = admin.packages.dependencies(reg.name, reg.version)
    inc = admin.contexts.include(
        "R4",
        IgRef(reg.name, reg.version),
        terminology=TerminologySettings(mode="server", server="https://tx.fhir.org/r4"),
    )
    print(inc.key, inc.resolved)  # hl7.fhir.uv.ips#1.1.0 [...]

    admin.contexts.update("R4", inc.key, AccessChange(shareable=False))
    admin.contexts.exclude("R4", inc.key)  # the package stays stored
```

## Packages: `client.packages`

| Method | Service operation | Notes |
|--------|-------------------|-------|
| `upload(archive, shareable=True)` | `POST /igs/upload` | path or binary file; streamed |
| `register(name, version="latest", download_url=None, include_dependencies=True, shareable=True)` | `POST /igs/register` | exactly one of `name` / `download_url`; version exact, `latest` or a series (`1.2.x`) |
| `update(name, version, AccessChange(...))` | `PATCH /igs/{name}/{version}` | `shareable` and/or `owner` |
| `dependencies(name, version)` | `GET …/dependencies` | VALIDATE key is enough |
| `files(name, version)` | `GET …/conformance` | **deprecated** by the service; emits `DeprecationWarning` |

## Validator contexts: `client.contexts`

| Method | Service operation | `ig` accepts |
|--------|-------------------|--------------|
| `include(fhir_version, ig, shareable=None, terminology=None)` | `POST /{version}/validator` | `name`, `name#1.2.0`, `name#latest`, `name#1.2.x`, or two IGs (`IgRef` tuple or `"a#1|b#2"`) |
| `exclude(fhir_version, ig)` | `DELETE /{version}/validator` | exact `name#version` or a two-IG key |
| `update(fhir_version, ig, AccessChange(...))` | `PATCH /{version}/validator` | exact `name#version` or a two-IG key |

`AccessChange` needs at least one of `shareable`, `owner` (an organisation's short name,
`^[A-Za-z0-9_-]{2,32}$`; ownership transfers are for system-organisation administrators only) and
`terminology` (contexts only).

## Retries

Administrative operations change state, so they are **not** retried by default. Pass
`retries=N` to a call (or set `RetryConfig(admin_max_retries=N)`) to retry 429/503 answers,
where the service did not perform the change. A connection failure or timeout is never retried
for these operations.
