"""Shared test fixtures.

* ``anyio_backend``: asyncio by default; the CI trio job sets ``FVS_TEST_ANYIO_BACKEND=trio``.
* ``mock_router``: canned responses per ``(method, path)`` served through ``httpx.MockTransport``.
* ``client``: a ``Client`` wired to ``mock_router``. ``fvs_client`` is imported *inside* the
  fixture so this module loads even before the client exists.
"""

from __future__ import annotations

import contextlib
import functools
import inspect
import json as _json
import os
import threading
from collections import defaultdict, deque
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

import httpx
import pytest
from anyio.from_thread import BlockingPortal, start_blocking_portal

if TYPE_CHECKING:
    from fvs_client import Client


@pytest.fixture
def anyio_backend() -> str:
    return os.environ.get("FVS_TEST_ANYIO_BACKEND", "asyncio")


Responder = Callable[[httpx.Request], httpx.Response]


@dataclass
class MockRouter:
    """Route table for ``httpx.MockTransport``.

    Each ``add`` call queues one response (or exception) for ``(method, path)``. Queued items
    are served in order; the last one is repeated once the queue is down to one item.
    """

    routes: dict[tuple[str, str], deque[httpx.Response | Exception | Responder]] = field(
        default_factory=lambda: defaultdict(deque)
    )
    requests: list[httpx.Request] = field(default_factory=list)
    in_flight: int = 0
    max_in_flight: int = 0
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def add(
        self,
        method: str,
        path: str,
        status: int = 200,
        *,
        json: Any = None,
        content: bytes | str | None = None,
        headers: Mapping[str, str] | None = None,
        content_type: str | None = None,
        exc: Exception | None = None,
        responder: Responder | None = None,
    ) -> MockRouter:
        key = (method.upper(), path)
        if exc is not None:
            self.routes[key].append(exc)
            return self
        if responder is not None:
            self.routes[key].append(responder)
            return self
        hdrs = dict(headers or {})
        body: bytes
        if json is not None:
            body = _json.dumps(json).encode()
            if not any(k.lower() == "content-type" for k in hdrs):
                hdrs["content-type"] = content_type or "application/json"
        elif isinstance(content, str):
            body = content.encode()
            if content_type:
                hdrs.setdefault("content-type", content_type)
        else:
            body = content or b""
            if content_type:
                hdrs.setdefault("content-type", content_type)
        if not any(k.lower() == "x-request-id" for k in hdrs):
            hdrs["x-request-id"] = f"req-{len(self.routes[key]) + 1}"
        self.routes[key].append(httpx.Response(status, headers=hdrs, content=body))
        return self

    def _next(self, request: httpx.Request) -> httpx.Response:
        key = (request.method, request.url.path)
        with self._lock:
            self.requests.append(request)
            queue = self.routes.get(key)
            if not queue:
                return httpx.Response(
                    404,
                    json={
                        "type": "https://nazrulworld.github.io/fhir-validation-service/problems/not-found",
                        "title": "Not found",
                        "status": 404,
                        "correlationId": "mock-unrouted",
                    },
                    headers={"content-type": "application/problem+json"},
                )
            item = queue.popleft() if len(queue) > 1 else queue[0]
        if isinstance(item, Exception):
            raise item
        if callable(item) and not isinstance(item, httpx.Response):
            return item(request)
        # Fresh copy so a repeated response can be read again.
        return httpx.Response(item.status_code, headers=item.headers, content=item.content)

    def handler(self, request: httpx.Request) -> httpx.Response:
        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            # Drain a streamed body so tests can inspect it.
            request.read()
            return self._next(request)
        finally:
            with self._lock:
                self.in_flight -= 1

    async def async_handler(self, request: httpx.Request) -> httpx.Response:
        import anyio.lowlevel

        with self._lock:
            self.in_flight += 1
            self.max_in_flight = max(self.max_in_flight, self.in_flight)
        try:
            await request.aread()
            await anyio.lowlevel.checkpoint()  # yield so concurrency is observable
            return self._next(request)
        finally:
            with self._lock:
                self.in_flight -= 1

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handler)

    def async_transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.async_handler)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]


@pytest.fixture
def mock_router() -> MockRouter:
    return MockRouter()


BASE_URL = "https://fvs.test"
API_KEY = "test-key"


ClientFactory = Callable[..., "Client"]


class SyncAdapter:
    """Presents an ``AsyncClient`` (or one of its sub-clients) with a synchronous interface.

    Coroutine methods run on an anyio blocking portal, so one scenario test exercises both
    clients identically.
    """

    def __init__(self, target: Any, portal: BlockingPortal) -> None:
        self._target = target
        self._portal = portal

    def __getattr__(self, name: str) -> Any:
        value = getattr(self._target, name)
        if inspect.iscoroutinefunction(value):

            def call(*args: Any, **kwargs: Any) -> Any:
                return self._portal.call(functools.partial(value, *args, **kwargs))

            return call
        if name in ("contexts", "packages", "health"):
            return SyncAdapter(value, self._portal)
        return value


@pytest.fixture(params=["sync", "async"])
def client_kind(request: pytest.FixtureRequest) -> str:
    return str(request.param)


@pytest.fixture
def make_client(
    mock_router: MockRouter, client_kind: str, anyio_backend: str
) -> Iterator[ClientFactory]:
    """Factory: ``make_client(**client_kwargs)`` → a client wired to ``mock_router``.

    Parametrised over the sync ``Client`` and the ``AsyncClient`` (through ``SyncAdapter``).
    """
    from fvs_client import AsyncClient, Client

    cleanups: list[Callable[[], None]] = []

    with contextlib.ExitStack() as stack:
        portal: BlockingPortal | None = None

        def factory(**kwargs: Any) -> Client:
            nonlocal portal
            kwargs.setdefault("api_key", API_KEY)
            if client_kind == "sync":
                http = httpx.Client(transport=mock_router.transport())
                c = Client(BASE_URL, http_client=http, **kwargs)
                cleanups.append(c.close)
                cleanups.append(http.close)
                return c
            if portal is None:
                portal = stack.enter_context(start_blocking_portal(backend=anyio_backend))
            ahttp = httpx.AsyncClient(transport=mock_router.async_transport())
            ac = AsyncClient(BASE_URL, http_client=ahttp, **kwargs)
            p = portal
            cleanups.append(lambda: p.call(ac.aclose))
            cleanups.append(lambda: p.call(ahttp.aclose))
            return SyncAdapter(ac, p)  # type: ignore[return-value]

        yield factory
        for cleanup in cleanups:
            cleanup()


@pytest.fixture
def client(make_client: ClientFactory) -> Client:
    return make_client()


@pytest.fixture
def sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record retry sleeps instead of waiting (patches ``time.sleep`` and ``anyio.sleep``)."""
    import time

    import anyio

    recorded: list[float] = []

    def fake_sleep(seconds: float) -> None:
        recorded.append(seconds)

    async def fake_async_sleep(seconds: float) -> None:
        recorded.append(seconds)
        await _real_anyio_sleep(0)

    _real_anyio_sleep = anyio.sleep
    monkeypatch.setattr(time, "sleep", fake_sleep)
    monkeypatch.setattr(anyio, "sleep", fake_async_sleep)
    return recorded
