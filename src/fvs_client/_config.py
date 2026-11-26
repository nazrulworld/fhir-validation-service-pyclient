"""Client settings: environment resolution, secret handling, timeouts and default headers."""

from __future__ import annotations

import os
import platform
from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from fvs_client.errors import InputError
from fvs_client.models import RetryConfig

ENV_BASE_URL = "FVS_BASE_URL"
ENV_API_KEY = "FVS_API_KEY"

DEFAULT_TIMEOUT = httpx.Timeout(60.0, connect=10.0)
"""60 s overall per phase, 10 s to connect (research R11)."""

_MASK = "**********"


class SecretStr:
    """Holds the API key; ``repr``/``str`` never reveal it."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def get_secret_value(self) -> str:
        """Return the secret itself (only for building the ``Authorization`` header)."""
        return self._value

    def __repr__(self) -> str:
        return repr(_MASK)

    def __str__(self) -> str:
        return _MASK

    def __eq__(self, other: object) -> bool:
        return isinstance(other, SecretStr) and other._value == self._value

    def __hash__(self) -> int:
        return hash(self._value)


def check_timeout(timeout: float | httpx.Timeout | None) -> httpx.Timeout:
    """Return a bounded ``httpx.Timeout`` (Constitution IV: no unbounded waits).

    Raises:
        InputError: ``timeout`` is ``None``, not positive, or an ``httpx.Timeout`` with any
            ``None`` (unbounded) phase.
    """
    if timeout is None:
        raise InputError("timeout must be set: None (wait forever) is not allowed")
    if isinstance(timeout, httpx.Timeout):
        phases = (timeout.connect, timeout.read, timeout.write, timeout.pool)
        if any(p is None for p in phases):
            raise InputError("timeout must bound every phase: connect, read, write and pool")
        if any(p is not None and p <= 0 for p in phases):
            raise InputError("timeout phases must be positive")
        return timeout
    if isinstance(timeout, bool) or not isinstance(timeout, int | float):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise InputError("timeout must be a number of seconds or an httpx.Timeout")
    if timeout <= 0:
        raise InputError("timeout must be positive")
    return httpx.Timeout(float(timeout))


def check_extra_headers(headers: Mapping[str, str] | None) -> dict[str, str]:
    """Return ``headers`` as a dict, refusing ``Authorization`` (set it with ``api_key``).

    Raises:
        InputError: ``headers`` contains ``Authorization`` in any letter case.
    """
    if not headers:
        return {}
    if any(k.lower() == "authorization" for k in headers):
        raise InputError("The Authorization header cannot be set directly; pass api_key instead")
    return dict(headers)


def _version() -> str:
    from fvs_client import __version__  # noqa: PLC0415 - package root imports this module

    return __version__


def build_user_agent(suffix: str | None) -> str:
    """Return ``fvs-client/<v> httpx/<v> python/<v>[ <suffix>]``."""
    ua = f"fvs-client/{_version()} httpx/{httpx.__version__} python/{platform.python_version()}"
    return f"{ua} {suffix}" if suffix else ua


def _check_base_url(value: str) -> str:
    try:
        url = httpx.URL(value.strip())
    except (httpx.InvalidURL, TypeError) as exc:
        raise InputError(f"base_url is not a valid URL: {value!r}") from exc
    if url.scheme not in ("http", "https") or not url.host:
        raise InputError(f"base_url must be an absolute http(s) URL, got {value!r}")
    if url.query or url.fragment:
        raise InputError("base_url must not contain a query or fragment")
    return str(url.copy_with(path=url.path.rstrip("/") or "/")).rstrip("/")


@dataclass(frozen=True, slots=True)
class Settings:
    """Resolved, validated client settings."""

    base_url: str
    api_key: SecretStr | None
    timeout: httpx.Timeout
    headers: Mapping[str, str]
    user_agent: str
    retry: RetryConfig


def resolve_settings(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    timeout: float | httpx.Timeout | None = DEFAULT_TIMEOUT,
    headers: Mapping[str, str] | None = None,
    user_agent_suffix: str | None = None,
    retries: RetryConfig | int | None = None,
) -> Settings:
    """Resolve arguments and environment (``FVS_BASE_URL``, ``FVS_API_KEY``) into ``Settings``.

    Raises:
        InputError: no base URL anywhere, or any argument breaks its rules.
    """
    url = base_url if base_url is not None else os.environ.get(ENV_BASE_URL)
    if not url:
        raise InputError(f"base_url is required: pass it or set the {ENV_BASE_URL} variable")
    key = api_key if api_key is not None else os.environ.get(ENV_API_KEY)
    if isinstance(retries, bool):
        raise InputError("retries must be a RetryConfig or an int")
    if retries is None:
        retry = RetryConfig()
    elif isinstance(retries, int):
        retry = RetryConfig(max_retries=retries)
    else:
        retry = retries
    return Settings(
        base_url=_check_base_url(url),
        api_key=SecretStr(key) if key else None,
        timeout=check_timeout(timeout),
        headers=check_extra_headers(headers),
        user_agent=build_user_agent(user_agent_suffix),
        retry=retry,
    )
