# Health checks

The health endpoints need **no API key**, so a client created without one can use them (for
example, a deployment gate).

```python
from fvs_client import Client

with Client("https://fvs.example.org") as fvs:
    fvs.health.liveness().status  # HealthStatus.UP
    ready = fvs.health.readiness()
    if not ready.is_ready:
        print("not ready:", ready.reasons)
    health = fvs.health.check()
    print(health.database.status, health.served_fhir_versions, health.acl_enabled)
```

| Method | Endpoint | Result |
|--------|----------|--------|
| `liveness()` | `GET /health/liveness` | `LivenessReport(status, timestamp)` |
| `readiness()` | `GET /health/readiness` | `ReadinessReport(status, reasons, catalog_revision, versions, is_ready)` |
| `check()` | `GET /health` | `HealthReport(status, database, readiness, served_fhir_versions, inactive_contexts, terminology_allowlist, acl_enabled, is_healthy)` |

## Not ready is an answer, not an error

When the service answers **503 with a report** (starting up, draining, or a context still
building), `readiness()` and `check()` **return** the report with `is_ready` / `is_healthy` set
to `False`. They do not raise, and they do not retry. A 503 *problem* document (for example
`overloaded`) or an empty 503 still raises `ServiceUnavailableError`.

Timestamps are timezone-aware UTC `datetime`s. `ReadinessReport.versions` is kept as plain data,
because its nested shape is described only loosely by the service.
