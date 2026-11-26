"""Sync transport and client lifecycle (T019)."""

from __future__ import annotations

import httpx
import pytest

from fvs_client import Client, FVSConnectionError, FVSTimeoutError, InputError, RawResponse
from fvs_client._requests import RequestSpec
from tests.conftest import MockRouter

SPEC = RequestSpec(method="GET", path="/health/liveness", accept="application/json")


def _send(c: Client, **kwargs: object) -> RawResponse:
    return c._request(SPEC, lambda raw: raw, **kwargs)  # type: ignore[arg-type]  # pyright: ignore[reportPrivateUsage]


def test_authorization_only_when_key_configured(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", json={"status": "UP"})
    http = httpx.Client(transport=mock_router.transport())
    with Client("https://fvs.test", api_key="k1", http_client=http) as c:
        _send(c)
    assert mock_router.last.headers["Authorization"] == "Bearer k1"
    with Client("https://fvs.test", http_client=http) as c:
        _send(c)
    assert "Authorization" not in mock_router.last.headers
    http.close()


def test_user_agent_accept_and_url(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/base/health/liveness", json={"status": "UP"})
    http = httpx.Client(transport=mock_router.transport())
    with Client(
        "https://fvs.test/base/", http_client=http, user_agent_suffix="app/1", headers={"X-A": "1"}
    ) as c:
        raw = _send(c, extra_headers={"X-B": "2"})
    req = mock_router.last
    assert str(req.url) == "https://fvs.test/base/health/liveness"
    assert req.headers["User-Agent"].startswith("fvs-client/")
    assert req.headers["User-Agent"].endswith(" app/1")
    assert req.headers["Accept"] == "application/json"
    assert req.headers["X-A"] == "1"
    assert req.headers["X-B"] == "2"
    assert raw.status_code == 200
    assert raw.meta.attempts == 1
    assert raw.meta.elapsed_seconds >= 0
    http.close()


def test_extra_headers_cannot_set_authorization(mock_router: MockRouter) -> None:
    http = httpx.Client(transport=mock_router.transport())
    with Client("https://fvs.test", http_client=http) as c, pytest.raises(InputError):
        _send(c, extra_headers={"AUTHORIZATION": "Bearer x"})
    assert mock_router.requests == []
    http.close()


def test_connect_error_maps_to_fvs_connection_error(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", exc=httpx.ConnectError("refused"))
    http = httpx.Client(transport=mock_router.transport())
    with (
        Client("https://fvs.test", http_client=http, retries=0) as c,
        pytest.raises(FVSConnectionError) as exc_info,
    ):
        _send(c)
    assert isinstance(exc_info.value.__cause__, httpx.ConnectError)
    http.close()


def test_other_transport_error_maps_to_fvs_connection_error(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", exc=httpx.RemoteProtocolError("bad"))
    http = httpx.Client(transport=mock_router.transport())
    with (
        Client("https://fvs.test", http_client=http, retries=0) as c,
        pytest.raises(FVSConnectionError),
    ):
        _send(c)
    http.close()


def test_timeout_maps_to_fvs_timeout_error(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", exc=httpx.ReadTimeout("slow"))
    http = httpx.Client(transport=mock_router.transport())
    with (
        Client("https://fvs.test", http_client=http) as c,
        pytest.raises(FVSTimeoutError) as exc_info,
    ):
        _send(c)
    assert isinstance(exc_info.value.__cause__, httpx.ReadTimeout)
    http.close()


def test_per_call_timeout_is_applied(mock_router: MockRouter) -> None:
    mock_router.add("GET", "/health/liveness", json={})
    http = httpx.Client(transport=mock_router.transport())
    with Client("https://fvs.test", http_client=http, timeout=30) as c:
        _send(c)
        assert mock_router.last.extensions["timeout"]["read"] == 30.0
        _send(c, timeout=2.5)
        assert mock_router.last.extensions["timeout"]["read"] == 2.5
        _send(c, timeout=None)
        assert mock_router.last.extensions["timeout"]["read"] == 30.0
    http.close()


def test_caller_supplied_client_is_not_closed(mock_router: MockRouter) -> None:
    http = httpx.Client(transport=mock_router.transport())
    c = Client("https://fvs.test", http_client=http)
    c.close()
    assert not http.is_closed
    http.close()


def test_owned_client_is_closed_by_close_and_context_manager() -> None:
    c = Client("https://fvs.test")
    owned = c._http  # pyright: ignore[reportPrivateUsage]
    c.close()
    assert owned.is_closed
    with Client("https://fvs.test") as c2:
        owned2 = c2._http  # pyright: ignore[reportPrivateUsage]
        assert not owned2.is_closed
    assert owned2.is_closed
