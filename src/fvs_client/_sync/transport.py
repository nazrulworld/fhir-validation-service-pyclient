"""Synchronous send loop: builds the httpx request, maps transport errors, applies retries."""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Mapping
from typing import cast

import httpx

from fvs_client._config import Settings
from fvs_client._logging import log_attempt, log_retry
from fvs_client._parsing import build_meta, build_raw, is_report
from fvs_client._requests import RequestSpec, request_headers, request_kwargs
from fvs_client._retry import RetryPolicy
from fvs_client.errors import FVSConnectionError, FVSTimeoutError, TransportError
from fvs_client.models import RawResponse


class SyncTransport:
    """Sends ``RequestSpec`` objects with an ``httpx.Client``."""

    def __init__(
        self,
        http: httpx.Client,
        settings: Settings,
        *,
        sleep: Callable[[float], None] | None = None,
        clock: Callable[[], float] = time.perf_counter,
        rng: random.Random | None = None,
    ) -> None:
        self._http = http
        self._settings = settings
        self._sleep = sleep
        self._clock = clock
        self._policy = RetryPolicy(settings.retry, rng=rng)

    def send(
        self,
        spec: RequestSpec,
        *,
        timeout: httpx.Timeout,
        extra_headers: Mapping[str, str],
        retries: int | None = None,
    ) -> RawResponse:
        """Send ``spec``, retrying per the policy, and return the final raw response.

        Raises:
            FVSConnectionError: the service could not be reached (after retries).
            FVSTimeoutError: the service did not answer in time.
        """
        url, headers = request_headers(self._settings, spec, extra_headers)
        attempt = 0
        while True:
            attempt += 1
            start = self._clock()
            raw: RawResponse | None = None
            error: TransportError | None = None
            try:
                request = self._http.build_request(
                    spec.method,
                    url,
                    params=dict(spec.params) or None,
                    headers=headers,
                    timeout=timeout,
                    **request_kwargs(spec, asynchronous=False),
                )
                response = self._http.send(request)
            except httpx.TimeoutException as exc:
                error = FVSTimeoutError(
                    f"{spec.method} {spec.path} timed out ({type(exc).__name__})"
                )
                error.__cause__ = exc
            except httpx.TransportError as exc:
                error = FVSConnectionError(
                    f"{spec.method} {spec.path} failed: {type(exc).__name__}: {exc}"
                )
                error.__cause__ = exc
            else:
                elapsed = self._clock() - start
                pairs = response.headers.multi_items()
                meta = build_meta(response.status_code, pairs, elapsed, attempt)
                raw = build_raw(response.status_code, pairs, response.content, meta)
            elapsed = self._clock() - start
            log_attempt(
                method=spec.method,
                path=spec.path,
                outcome=raw.status_code if raw is not None else type(error).__name__,
                elapsed=elapsed,
                request_id=raw.meta.request_id if raw is not None else None,
                attempt=attempt,
            )
            delay = self._policy.decide(
                attempt,
                is_admin=spec.is_admin,
                raw=raw,
                exc=error,
                override=retries,
                retry_503=not (spec.report_on_503 and raw is not None and is_report(raw)),
            )
            if delay is None:
                if raw is not None:
                    return raw
                raise cast("TransportError", error)
            log_retry(
                method=spec.method,
                path=spec.path,
                attempt=attempt,
                delay=delay,
                reason=str(raw.status_code) if raw is not None else type(error).__name__,
            )
            (self._sleep or time.sleep)(delay)
