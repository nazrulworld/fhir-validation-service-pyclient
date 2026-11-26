"""Retry decisions (pure: no sleeping, no I/O).

Rules (research R10, spec FR-022):

* 429 and 503: wait ``Retry-After`` when given (an advised wait longer than
  ``max_retry_after`` raises at once), otherwise a full-jitter exponential backoff;
* connection failures (``httpx.ConnectError``: nothing was sent): backoff, safe operations only;
* timeouts and every other status/error: never retried;
* safe operations retry up to ``max_retries``; administrative ones up to ``admin_max_retries``
  (default 0), and only for 429/503, where the service did not perform the change.
"""

from __future__ import annotations

import random

import httpx

from fvs_client.errors import FVSConnectionError, TransportError
from fvs_client.models import RawResponse, RetryConfig

_RETRY_STATUSES = frozenset({429, 503})


class RetryPolicy:
    """Decides whether, and how long, to wait before another attempt."""

    def __init__(self, config: RetryConfig, *, rng: random.Random | None = None) -> None:
        self.config = config
        self._rng = rng or random.Random()  # noqa: S311 - jitter, not cryptography

    def max_retries(self, *, is_admin: bool, override: int | None = None) -> int:
        """Retries allowed for this operation."""
        if override is not None:
            return max(0, override)
        return self.config.admin_max_retries if is_admin else self.config.max_retries

    def backoff(self, attempt: int) -> float:
        """Full-jitter backoff: uniform in ``[0, min(max, base * 2**(attempt - 1))]``."""
        ceiling = min(self.config.backoff_max, self.config.backoff_base * 2 ** (attempt - 1))
        return self._rng.uniform(0.0, ceiling)

    def decide(
        self,
        attempt: int,
        *,
        is_admin: bool,
        raw: RawResponse | None,
        exc: TransportError | None,
        override: int | None = None,
        retry_503: bool = True,
    ) -> float | None:
        """Return seconds to wait before attempt ``attempt + 1``, or ``None`` to stop.

        Args:
            attempt: Number of attempts made so far (1 after the first).
            is_admin: The operation changes state (administrative).
            raw: The response of the attempt, if one was received.
            exc: The transport error of the attempt, if any.
            override: Per-call retry count replacing the configured one.
            retry_503: False when a 503 carries a report to return (health endpoints).
        """
        if attempt > self.max_retries(is_admin=is_admin, override=override):
            return None
        if exc is not None:
            connect_failed = isinstance(exc, FVSConnectionError) and isinstance(
                exc.__cause__, httpx.ConnectError
            )
            return self.backoff(attempt) if connect_failed and not is_admin else None
        if raw is None or raw.status_code not in _RETRY_STATUSES:
            return None
        if raw.status_code == 503 and not retry_503:
            return None
        return self._status_delay(raw, attempt)

    def _status_delay(self, raw: RawResponse, attempt: int) -> float | None:
        advised = raw.meta.rate_limit.retry_after_seconds
        if advised is None:
            return self.backoff(attempt)
        if advised > self.config.max_retry_after:
            return None
        return float(max(0, advised))
