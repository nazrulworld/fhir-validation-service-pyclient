"""The ``fvs_client`` logger.

Silent by default (``NullHandler``). Records never contain headers, bodies, query values or the
API key: only method, path, status, timing, request id and attempt number.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping

logger = logging.getLogger("fvs_client")
logger.addHandler(logging.NullHandler())

_MASK = "**********"


def redact_headers(headers: Mapping[str, str]) -> dict[str, str]:
    """Return a copy of ``headers`` with the ``Authorization`` value masked."""
    return {k: (_MASK if k.lower() == "authorization" else v) for k, v in headers.items()}


def log_attempt(
    *,
    method: str,
    path: str,
    outcome: int | str,
    elapsed: float,
    request_id: str | None,
    attempt: int,
) -> None:
    """Log one HTTP attempt at DEBUG (``outcome`` is the status or an exception class name)."""
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(
            "%s %s -> %s in %.1f ms (request id %s, attempt %d)",
            method,
            path,
            outcome,
            elapsed * 1000.0,
            request_id or "-",
            attempt,
        )


def log_retry(*, method: str, path: str, attempt: int, delay: float, reason: str) -> None:
    """Log a retry decision at INFO."""
    logger.info(
        "%s %s: retrying after %.2f s (attempt %d failed: %s)", method, path, delay, attempt, reason
    )
