# Installation

```bash
pip install fvs_client
# or
uv add fvs_client
```

`fvs_client` needs Python 3.11 or newer. It depends only on
[`httpx`](https://www.python-httpx.org/) and [`anyio`](https://anyio.readthedocs.io/).

## Configuration

| Argument | Environment variable | Default |
|----------|----------------------|---------|
| `base_url` | `FVS_BASE_URL` | required |
| `api_key` | `FVS_API_KEY` | none |
| `timeout` | | 60 s per phase, 10 s to connect |
| `retries` | | `RetryConfig()`: 2 retries for safe operations, 0 for administrative ones |
| `headers` | | none (`Authorization` is not allowed; use `api_key`) |
| `user_agent_suffix` | | none |

The API key is sent as `Authorization: Bearer <key>`. It never appears in `repr()`, error
messages or logs.

Health checks need no key, and neither does any call on a deployment that runs with access
control disabled ("public mode").

## Proxies, custom TLS and testing

Pass your own `httpx.Client` (or `httpx.AsyncClient` for `AsyncClient`). The SDK uses it as-is
and never closes it:

```python
import httpx
from fvs_client import Client

http = httpx.Client(proxy="http://proxy.internal:3128", verify="/etc/ssl/internal-ca.pem")
fvs = Client("https://fvs.internal", api_key="…", http_client=http)
```

!!! warning "TLS verification"
    TLS certificates are verified by default. Turning verification off
    (`httpx.Client(verify=False)`) exposes the API key and patient data to interception;
    do it only on a trusted test network.

## Logging

The SDK logs to the `fvs_client` logger, which is silent unless you configure it:

```python
import logging

logging.getLogger("fvs_client").setLevel(logging.DEBUG)
logging.basicConfig()
```

It logs method, path, status, duration, request id and attempt number. It never logs headers,
bodies, the API key or terminology server addresses.
