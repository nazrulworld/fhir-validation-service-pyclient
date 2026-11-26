"""Retry decisions: every row of contracts/http-mapping.md#retry-decision-table (T045)."""

from __future__ import annotations

import random

import httpx
import pytest

from fvs_client import FVSConnectionError, FVSTimeoutError, RetryConfig
from fvs_client._parsing import build_meta, build_raw
from fvs_client._retry import RetryPolicy
from fvs_client.models import RawResponse


def _raw(status: int, headers: dict[str, str] | None = None) -> RawResponse:
    h = headers or {}
    return build_raw(status, h, b"", build_meta(status, h, 0.0, 1))


def _connect_error() -> FVSConnectionError:
    err = FVSConnectionError("refused")
    err.__cause__ = httpx.ConnectError("refused")
    return err


def _read_error() -> FVSConnectionError:
    err = FVSConnectionError("reset")
    err.__cause__ = httpx.ReadError("reset")
    return err


def _timeout() -> FVSTimeoutError:
    err = FVSTimeoutError("slow")
    err.__cause__ = httpx.ReadTimeout("slow")
    return err


POLICY = RetryPolicy(RetryConfig(), rng=random.Random(1))


# --------------------------------------------------------------------------- 429


def test_429_waits_exactly_retry_after() -> None:
    assert POLICY.decide(1, is_admin=False, raw=_raw(429, {"Retry-After": "12"}), exc=None) == 12.0


def test_429_retry_after_at_cap_is_waited() -> None:
    assert POLICY.decide(1, is_admin=False, raw=_raw(429, {"Retry-After": "60"}), exc=None) == 60.0


def test_429_retry_after_over_cap_raises_at_once() -> None:
    assert POLICY.decide(1, is_admin=False, raw=_raw(429, {"Retry-After": "61"}), exc=None) is None


def test_429_without_retry_after_uses_backoff() -> None:
    delay = POLICY.decide(1, is_admin=False, raw=_raw(429), exc=None)
    assert delay is not None
    assert 0.0 <= delay <= 0.5


def test_retry_after_zero() -> None:
    assert POLICY.decide(1, is_admin=False, raw=_raw(429, {"Retry-After": "0"}), exc=None) == 0.0


# --------------------------------------------------------------------------- 503 / backoff


def test_503_with_retry_after() -> None:
    assert POLICY.decide(1, is_admin=False, raw=_raw(503, {"Retry-After": "2"}), exc=None) == 2.0


@pytest.mark.parametrize("attempt", [1, 2, 3, 4, 5, 6, 7])
def test_503_without_retry_after_full_jitter_bounds(attempt: int) -> None:
    config = RetryConfig(max_retries=10)
    ceiling = min(config.backoff_max, config.backoff_base * 2 ** (attempt - 1))
    policy = RetryPolicy(config, rng=random.Random(attempt))
    delays = [policy.decide(attempt, is_admin=False, raw=_raw(503), exc=None) for _ in range(200)]
    assert all(d is not None and 0.0 <= d <= ceiling for d in delays)
    assert max(d for d in delays if d is not None) > ceiling / 2  # actually jittered over the range


def test_503_report_not_retried_when_disallowed() -> None:
    assert POLICY.decide(1, is_admin=False, raw=_raw(503), exc=None, retry_503=False) is None


# --------------------------------------------------------------------------- transport errors


def test_connect_error_retried_for_safe_ops() -> None:
    delay = POLICY.decide(1, is_admin=False, raw=None, exc=_connect_error())
    assert delay is not None
    assert 0.0 <= delay <= 0.5


def test_connect_error_never_retried_for_admin_ops() -> None:
    policy = RetryPolicy(RetryConfig(admin_max_retries=5))
    assert policy.decide(1, is_admin=True, raw=None, exc=_connect_error()) is None


@pytest.mark.parametrize("exc", [_timeout(), _read_error()])
def test_timeouts_and_other_transport_errors_never_retried(exc: Exception) -> None:
    assert POLICY.decide(1, is_admin=False, raw=None, exc=exc) is None  # type: ignore[arg-type]


@pytest.mark.parametrize("status", [200, 400, 401, 404, 409, 500, 502, 504])
def test_other_statuses_never_retried(status: int) -> None:
    assert (
        POLICY.decide(1, is_admin=False, raw=_raw(status, {"Retry-After": "1"}), exc=None) is None
    )


# --------------------------------------------------------------------------- attempt limits


def test_safe_ops_stop_after_max_retries() -> None:
    raw = _raw(503, {"Retry-After": "1"})
    assert POLICY.decide(1, is_admin=False, raw=raw, exc=None) == 1.0
    assert POLICY.decide(2, is_admin=False, raw=raw, exc=None) == 1.0
    assert POLICY.decide(3, is_admin=False, raw=raw, exc=None) is None  # 2 retries done


def test_admin_ops_default_to_no_retry() -> None:
    raw = _raw(429, {"Retry-After": "1"})
    assert POLICY.decide(1, is_admin=True, raw=raw, exc=None) is None


def test_admin_retry_when_enabled_covers_429_and_503_only() -> None:
    policy = RetryPolicy(RetryConfig(admin_max_retries=1))
    assert policy.decide(1, is_admin=True, raw=_raw(429, {"Retry-After": "1"}), exc=None) == 1.0
    assert policy.decide(1, is_admin=True, raw=_raw(503, {"Retry-After": "1"}), exc=None) == 1.0
    assert policy.decide(2, is_admin=True, raw=_raw(503, {"Retry-After": "1"}), exc=None) is None
    assert policy.decide(1, is_admin=True, raw=None, exc=_connect_error()) is None
    assert policy.decide(1, is_admin=True, raw=None, exc=_timeout()) is None


def test_per_call_override() -> None:
    raw = _raw(503, {"Retry-After": "1"})
    assert POLICY.decide(1, is_admin=True, raw=raw, exc=None, override=1) == 1.0
    assert POLICY.decide(2, is_admin=True, raw=raw, exc=None, override=1) is None
    assert POLICY.decide(1, is_admin=False, raw=raw, exc=None, override=0) is None


def test_zero_retries_never_retries() -> None:
    policy = RetryPolicy(RetryConfig(max_retries=0))
    assert policy.decide(1, is_admin=False, raw=_raw(429, {"Retry-After": "1"}), exc=None) is None
    assert policy.decide(1, is_admin=False, raw=None, exc=_connect_error()) is None
