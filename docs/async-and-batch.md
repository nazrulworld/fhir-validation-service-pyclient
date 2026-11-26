# Async & batch validation

## AsyncClient

`AsyncClient` has exactly the same operations, arguments, results and errors as `Client`; only
the call style differs. It works on asyncio and trio (via [AnyIO](https://anyio.readthedocs.io/)).

```python
import anyio
from fvs_client import AsyncClient


async def main() -> None:
    async with AsyncClient("http://127.0.0.1:8880", api_key="…") as fvs:
        result = await fvs.validate({"resourceType": "Patient"}, fhir_version="R4")
        print(result.valid)


anyio.run(main)
```

Pass `http_client=httpx.AsyncClient(...)` to use your own transport settings; the SDK never
closes a client you pass in.

## Validating many resources

`validate_many` validates resources concurrently, with at most `concurrency` requests in flight
(default 8), and returns one entry per input **in input order**:

```python
results = await fvs.validate_many(resources, fhir_version="R4", concurrency=10)
for resource, outcome in zip(resources, results):
    if isinstance(outcome, Exception):  # an FVSError, e.g. RateLimitError or InputError
        print("failed:", outcome)
    elif not outcome.valid:
        print("invalid:", [i.message for i in outcome.errors])
```

- Each failure (including an `InputError` for one bad resource) is placed in that resource's
  slot; the other resources still run.
- Options shared by the batch (FHIR version, IG, profiles, …) are checked once, before anything
  is sent, and raise `InputError` straight away.
- `Client.validate_many` does the same with a thread pool sharing one connection pool.
- Retries and `Retry-After` apply per request, so a rate-limited batch slows down instead of
  failing (see [Errors & retries](errors-and-retries.md)).
