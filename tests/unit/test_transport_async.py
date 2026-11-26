"""Async transport and AsyncClient lifecycle (T062): mirrors test_transport_sync.py."""

from __future__ import annotations

import httpx
import pytest

from fvs_client import AsyncClient, FVSConnectionError, FVSTimeoutError, InputError, RawResponse
from fvs_client._requests import RequestSpec
from tests.conftest import MockRouter

pytestmark = pytest.mark.anyio

SPEC = RequestSpec(method="GET", path="/health/liveness", accept="application/json")
RETRYABLE = RequestSpec(method="POST", path="/R4/validate", accept="application/json")


async def _send(c: AsyncClient, spec: RequestSpec = SPEC, **kwargs: object) -> RawResponse:
    return await c._request(spec, lambda raw: raw, **kwargs)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]


async def test_authorization_only_when_key_configured(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", json={"status": "UP"})
    async with httpx.AsyncClient(transport=mock_router.async_transport()) as http:
        async with AsyncClient("https://fvs.test", api_key="k1", http_client=http) as c:
            await _send(c)
        assert mock_router.last.headers["Authorization"] == "Bearer k1"
        async with AsyncClient("https://fvs.test", http_client=http) as c:
            await _send(c)
        assert "Authorization" not in mock_router.last.headers


async def test_headers_url_and_meta(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/base/health/liveness", json={"status": "UP"})
    async with (
        httpx.AsyncClient(transport=mock_router.async_transport()) as http,
        AsyncClient("https://fvs.test/base", http_client=http, user_agent_suffix="app/1") as c,
    ):
        raw = await _send(c, extra_headers={"X-B": "2"})
    req = mock_router.last
    assert str(req.url) == "https://fvs.test/base/health/liveness"
    assert req.headers["User-Agent"].endswith(" app/1")
    assert req.headers["X-B"] == "2"
    assert raw.meta.attempts == 1


async def test_extra_headers_cannot_set_authorization(mock_router: MockRouter) -> None:
    async with (
        httpx.AsyncClient(transport=mock_router.async_transport()) as http,
        AsyncClient("https://fvs.test", http_client=http) as c,
    ):
        with pytest.raises(InputError):
            await _send(c, extra_headers={"Authorization": "x"})
    assert mock_router.requests == []


async def test_exceptions_are_mapped(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", exc=httpx.ConnectError("refused"))
    mock_router.add("GET", "/R4/validate", exc=httpx.ReadTimeout("slow"))
    async with (
        httpx.AsyncClient(transport=mock_router.async_transport()) as http,
        AsyncClient("https://fvs.test", http_client=http, retries=0) as c,
    ):
        with pytest.raises(FVSConnectionError) as info:
            await _send(c)
        assert isinstance(info.value.__cause__, httpx.ConnectError)
        mock_router.routes.clear()
        mock_router.add("GET", "/health/liveness", exc=httpx.ReadTimeout("slow"))
        with pytest.raises(FVSTimeoutError) as info2:
            await _send(c)
        assert isinstance(info2.value.__cause__, httpx.ReadTimeout)


async def test_retry_awaits_the_decided_delay(mock_router: MockRouter, sleeps: list[float]) -> None:
    mock_router.add("POST", "/R4/validate", 429, json={}, headers={"Retry-After": "3"})
    mock_router.add("POST", "/R4/validate", json={"valid": True})
    async with (
        httpx.AsyncClient(transport=mock_router.async_transport()) as http,
        AsyncClient("https://fvs.test", http_client=http) as c,
    ):
        raw = await _send(c, RETRYABLE)
    assert raw.status_code == 200
    assert raw.meta.attempts == 2
    assert sleeps == [3.0]


async def test_caller_supplied_client_is_not_closed(mock_router: MockRouter) -> None:
    http = httpx.AsyncClient(transport=mock_router.async_transport())
    c = AsyncClient("https://fvs.test", http_client=http)
    await c.aclose()
    assert not http.is_closed
    await http.aclose()


async def test_owned_client_closed_by_aclose_and_context_manager() -> None:
    c = AsyncClient("https://fvs.test")
    owned = c._http  # pyright: ignore[reportPrivateUsage]
    await c.aclose()
    assert owned.is_closed
    async with AsyncClient("https://fvs.test") as c2:
        owned2 = c2._http  # pyright: ignore[reportPrivateUsage]
        assert not owned2.is_closed
    assert owned2.is_closed


async def test_repr_masks_key() -> None:
    async with AsyncClient("https://fvs.test", api_key="s3cr3t") as c:
        assert "s3cr3t" not in repr(c)
        assert repr(c).startswith("AsyncClient(")
