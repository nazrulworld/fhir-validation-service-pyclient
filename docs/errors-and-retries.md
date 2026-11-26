# Errors & retries

```text
FVSError
├── InputError(FVSError, ValueError)     # a local check failed; nothing was sent
├── TransportError
│   ├── FVSConnectionError
│   └── FVSTimeoutError
└── APIError                              # .status_code .problem .problem_type .request_id .response
    ├── BadRequestError                   # 400 405 406 413 415 422 424
    │   ├── InvalidResourceError          # .issues
    │   ├── UnknownProfileError           # .unresolved_profiles
    │   └── DependencyConflictError       # .conflicts
    ├── AuthenticationError               # 401
    ├── PermissionDeniedError             # 403
    ├── NotFoundError                     # 404
    ├── ConflictError                     # 409
    ├── RateLimitError                    # 429 .scope .limit .retry_after
    ├── ServiceUnavailableError           # 503 .retry_after
    └── ServerError                       # 500 and other 5xx
```

A completed validation of an invalid resource is **not** an error.

## Problem types

The service answers errors with RFC 9457 problem documents whose `type` is a URI such as
`https://nazrulworld.github.io/fhir-validation-service/problems/rate-limited`.
`error.problem_type` is its short name as a `ProblemType` member (or a `str` for a type this SDK
version doesn't know), so you can branch on it:

```python
from fvs_client import APIError, ProblemType

try:
    fvs.validate(r, fhir_version="R4", ig="my.ig#1.0.0")
except APIError as e:
    if e.problem_type is ProblemType.PACKAGE_NOT_FOUND:
        ...
    print(e.request_id)  # quote it when reporting a problem to the operator
```

## Retries

| Condition | Safe operations (validation, health, package reads) | Administrative operations |
|-----------|-----------------------------------------------------|---------------------------|
| 429 / 503 | waits `Retry-After` (or a jittered backoff), up to `max_retries` (2) | only if `admin_max_retries` / `retries=` allow (default 0) |
| `Retry-After` > `max_retry_after` (60 s) | raised at once | raised at once |
| connection failure | retried with backoff | never |
| timeout, any other status | never | never |

```python
from fvs_client import Client, RetryConfig

Client(retries=0)  # no automatic retries
Client(retries=RetryConfig(max_retries=5, max_retry_after=120))
```

`result.meta.attempts` and `error.meta.attempts` show how many attempts were made, and
`meta.rate_limit` carries the `RateLimit-*` headers.
