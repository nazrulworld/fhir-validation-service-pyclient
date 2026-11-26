# Raw responses & plain data

## Raw mode

Every operation accepts `raw=True` and then returns the unparsed `RawResponse` instead of a
result model:

```python
raw = fvs.validate(resource, fhir_version="R4", raw=True)
raw.status_code  # 200
raw.headers["x-validation-context"]  # read-only, case-insensitive
raw.content  # bytes
raw.text  # decoded with the response charset
raw.json()  # decoded JSON
raw.meta.request_id  # also .rate_limit, .elapsed_seconds, .attempts
```

Error statuses still raise the typed error, and every `APIError` carries the same kind of
object in `error.response`.

## The original body on every result

Parsed results keep the service's body exactly as received in `raw`, so fields this SDK version
does not model are never lost:

```python
result = fvs.validate(resource, fhir_version="R4")
result.raw["someNewField"]
```

## Plain data

Every model is an immutable dataclass with `to_dict()`, which returns JSON-ready plain data
(enums become their values, datetimes become ISO 8601 strings):

```python
import json

json.dumps(result.to_dict())
```
