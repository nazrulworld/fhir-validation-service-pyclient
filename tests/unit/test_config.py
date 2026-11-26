"""Client configuration: env resolution, secrets, timeouts, headers, retry defaults (T015)."""

from __future__ import annotations

import platform

import httpx
import pytest

from fvs_client import Client, InputError, RetryConfig, __version__
from fvs_client._config import (
    DEFAULT_TIMEOUT,
    SecretStr,
    build_user_agent,
    check_extra_headers,
    check_timeout,
    resolve_settings,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("FVS_BASE_URL", raising=False)
    monkeypatch.delenv("FVS_API_KEY", raising=False)


def test_arguments_win_over_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FVS_BASE_URL", "https://env.example")
    monkeypatch.setenv("FVS_API_KEY", "env-key")
    s = resolve_settings(base_url="https://arg.example", api_key="arg-key")
    assert s.base_url == "https://arg.example"
    assert s.api_key is not None
    assert s.api_key.get_secret_value() == "arg-key"


def test_env_used_when_arguments_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FVS_BASE_URL", "https://env.example/")
    monkeypatch.setenv("FVS_API_KEY", "env-key")
    s = resolve_settings()
    assert s.base_url == "https://env.example"
    assert s.api_key is not None
    assert s.api_key.get_secret_value() == "env-key"


def test_api_key_may_be_absent() -> None:
    assert resolve_settings(base_url="https://x.example").api_key is None


def test_missing_base_url_is_input_error() -> None:
    with pytest.raises(InputError, match="FVS_BASE_URL"):
        resolve_settings()


@pytest.mark.parametrize("url", ["ftp://x.example", "x.example", "https://"])
def test_invalid_base_url_is_input_error(url: str) -> None:
    with pytest.raises(InputError):
        resolve_settings(base_url=url)


def test_trailing_slashes_are_normalised() -> None:
    assert resolve_settings(base_url="https://x.example/fvs//").base_url == "https://x.example/fvs"


def test_secret_str_never_shows_value() -> None:
    s = SecretStr("s3cr3t")
    assert repr(s) == "'**********'"
    assert str(s) == "**********"
    assert "s3cr3t" not in f"{s!r} {s!s} {s}"
    assert s.get_secret_value() == "s3cr3t"


def test_client_repr_masks_key() -> None:
    c = Client("https://x.example", api_key="s3cr3t")
    try:
        assert "s3cr3t" not in repr(c)
        assert "**********" in repr(c)
        assert "https://x.example" in repr(c)
    finally:
        c.close()


@pytest.mark.parametrize("name", ["Authorization", "authorization", "AUTHORIZATION"])
def test_authorization_not_allowed_in_default_headers(name: str) -> None:
    with pytest.raises(InputError, match="Authorization"):
        resolve_settings(base_url="https://x.example", headers={name: "Bearer x"})


def test_authorization_not_allowed_in_extra_headers() -> None:
    with pytest.raises(InputError, match="Authorization"):
        check_extra_headers({"authorization": "Bearer x"})
    assert check_extra_headers(None) == {}
    assert check_extra_headers({"X-Trace": "1"}) == {"X-Trace": "1"}


def test_default_timeout() -> None:
    assert httpx.Timeout(60.0, connect=10.0) == DEFAULT_TIMEOUT
    assert resolve_settings(base_url="https://x.example").timeout == DEFAULT_TIMEOUT


def test_float_timeout_is_accepted() -> None:
    assert check_timeout(5) == httpx.Timeout(5.0)


def test_none_timeout_is_rejected() -> None:
    with pytest.raises(InputError, match="timeout"):
        check_timeout(None)
    with pytest.raises(InputError, match="timeout"):
        Client("https://x.example", timeout=None)  # type: ignore[arg-type]


@pytest.mark.parametrize(
    "timeout",
    [httpx.Timeout(None), httpx.Timeout(10.0, read=None), httpx.Timeout(10.0, pool=None)],
)
def test_timeout_with_unbounded_field_is_rejected(timeout: httpx.Timeout) -> None:
    with pytest.raises(InputError, match="timeout"):
        check_timeout(timeout)


@pytest.mark.parametrize("value", [0, -1.0])
def test_non_positive_timeout_is_rejected(value: float) -> None:
    with pytest.raises(InputError):
        check_timeout(value)


def test_user_agent_format() -> None:
    ua = build_user_agent(None)
    assert ua == (
        f"fvs-client/{__version__} httpx/{httpx.__version__} python/{platform.python_version()}"
    )
    assert build_user_agent("my-app/1.2").endswith(" my-app/1.2")


def test_retry_config_defaults() -> None:
    r = RetryConfig()
    assert (
        r.max_retries,
        r.admin_max_retries,
        r.backoff_base,
        r.backoff_max,
        r.max_retry_after,
    ) == (
        2,
        0,
        0.5,
        8.0,
        60.0,
    )


def test_retries_int_sets_safe_max_retries() -> None:
    s = resolve_settings(base_url="https://x.example", retries=5)
    assert s.retry == RetryConfig(max_retries=5)


@pytest.mark.parametrize(
    "kwargs", [{"max_retries": -1}, {"backoff_base": -0.1}, {"max_retry_after": -1}]
)
def test_negative_retry_values_rejected(kwargs: dict[str, float]) -> None:
    with pytest.raises(InputError):
        RetryConfig(**kwargs)  # type: ignore[arg-type]
