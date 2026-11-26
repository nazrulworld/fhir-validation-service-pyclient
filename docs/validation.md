# Validation

```python
result = fvs.validate(resource, fhir_version="R4")
```

## Resources

| You pass | Sent as |
|----------|---------|
| `dict` | compact JSON, `application/fhir+json` |
| `str` / `bytes` starting with `{` | as-is, `application/fhir+json` |
| `str` / `bytes` starting with `<` | as-is, `application/fhir+xml` |
| `pathlib.Path` | streamed from disk; `.json`/`.xml` suffix decides, otherwise detected |

To send something else anyway, pass `content_type="…"`.

## FHIR version

`fhir_version` is `STU3`, `R4`, `R4B` or `R5` in any case, or a `FhirVersion` member. Any other
value raises `InputError` before anything is sent.

## Implementation Guides

```python
fvs.validate(r, fhir_version="R4", ig="hl7.fhir.uv.ips#1.1.0")  # exact version
fvs.validate(r, fhir_version="R4", ig="hl7.fhir.uv.ips")  # highest included version
fvs.validate(r, fhir_version="R4", ig=IgRef("a.ig", "1.0.0"))
fvs.validate(r, fhir_version="R4", ig="a.ig#1.0.0|b.ig#2.0.0")  # a two-IG context
```

`#` and `|` are percent-encoded for you. Version series such as `1.2.x` are rejected; use the
concrete version reported when the IG was included. `result.ig_package` and
`result.context.key` report what was actually used.

## Profiles and terminology

```python
fvs.validate(
    r,
    fhir_version="R4",
    profiles=["http://hl7.org/fhir/uv/ips/StructureDefinition/Patient-uv-ips"],  # ≤ 10
    tx="https://tx.fhir.org/r4",  # this request only
    tx_mode="server",  # none | server | ecosystem
)
```

`result.context.tx_mode`, `tx_server` and `tx_source` report the setting the service applied.

## Results

`ValidationResult` (the default):

| Attribute | Meaning |
|-----------|---------|
| `valid` | `False` if any FATAL/ERROR issue |
| `issues`, `errors`, `warnings`, `information` | `ValidationIssue(severity, location, message)` |
| `has_errors`, `issues_by_severity(...)` | helpers |
| `fhir_version`, `applied_profiles`, `ig_package`, `ig_owner`, `ig_shareable` | from the body |
| `context` | validator context and terminology setting (response headers) |
| `meta` | request id, rate-limit info, timing, attempts |
| `raw` | the body exactly as received |

Every result is immutable and has `to_dict()`.

### FHIR OperationOutcome

```python
from fvs_client import ResultFormat

oo = fvs.validate(r, fhir_version="R4", result_format=ResultFormat.OPERATION_OUTCOME_JSON)
oo.body["issue"]  # dict body
xml = fvs.validate(r, fhir_version="R4", result_format=ResultFormat.OPERATION_OUTCOME_XML)
xml.body  # str body
```

### Raw responses

`raw=True` returns the unparsed `RawResponse` (`status_code`, `headers`, `content`, `.text`,
`.json()`, `meta`). Error statuses still raise typed errors.

## Reusable options

```python
from fvs_client import ValidationOptions

opts = ValidationOptions(ig="hl7.fhir.uv.ips#1.1.0", tx_mode="none")
fvs.validate(r, fhir_version="R4", options=opts)
```

Options are checked when they are created. Pass either `options=` or keyword options, not both.
