"""Client and AsyncClient expose identical operations (T060, Constitution IV)."""

from __future__ import annotations

import inspect
import typing
from collections.abc import Callable
from typing import Any

import pytest

from fvs_client import AsyncClient, Client

SYNC_ONLY = {"close", "__enter__", "__exit__"}
ASYNC_ONLY = {"aclose", "__aenter__", "__aexit__"}
SUB_CLIENTS = ("contexts", "packages", "health")


def _public_methods(cls: type) -> dict[str, Callable[..., Any]]:
    return {
        name: member
        for name, member in vars(cls).items()
        if not name.startswith("_") and callable(member) and name not in SYNC_ONLY | ASYNC_ONLY
    }


def _shape(func: Callable[..., Any]) -> list[tuple[str, Any, Any, Any]]:
    sig = inspect.signature(func)
    return [(p.name, p.kind, p.default, p.annotation) for p in sig.parameters.values()]


def _pairs() -> list[tuple[type, type]]:
    pairs: list[tuple[type, type]] = [(Client, AsyncClient)]
    for attr in SUB_CLIENTS:
        s, a = getattr(Client, attr, None), getattr(AsyncClient, attr, None)
        assert (s is None) == (a is None), f"{attr} exists on only one client"
        if isinstance(s, property) and isinstance(a, property):
            assert s.fget is not None
            assert a.fget is not None
            sc = inspect.signature(s.fget, eval_str=True).return_annotation
            ac = inspect.signature(a.fget, eval_str=True).return_annotation
            pairs.append((sc, ac))
    return pairs


@pytest.mark.parametrize(("sync_cls", "async_cls"), _pairs(), ids=lambda c: c.__name__)
def test_same_methods_and_signatures(sync_cls: type, async_cls: type) -> None:
    sync_methods = _public_methods(sync_cls)
    async_methods = _public_methods(async_cls)
    assert sorted(sync_methods) == sorted(async_methods)
    for name, sync_func in sync_methods.items():
        async_func = async_methods[name]
        assert inspect.iscoroutinefunction(async_func), f"{async_cls.__name__}.{name} is not async"
        assert not inspect.iscoroutinefunction(sync_func)
        assert _shape(sync_func) == _shape(async_func), name
        assert (
            inspect.signature(sync_func).return_annotation
            == inspect.signature(async_func).return_annotation
        ), name
        sync_overloads = [_shape(f) for f in typing.get_overloads(sync_func)]
        async_overloads = [_shape(f) for f in typing.get_overloads(async_func)]
        assert sync_overloads == async_overloads, name


def test_constructors_match_except_http_client_type() -> None:
    sync_params = inspect.signature(Client.__init__).parameters
    async_params = inspect.signature(AsyncClient.__init__).parameters
    assert list(sync_params) == list(async_params)
    for name, p in sync_params.items():
        q = async_params[name]
        assert (p.kind, p.default) == (q.kind, q.default), name
        if name != "http_client":
            assert p.annotation == q.annotation, name
    assert "httpx.AsyncClient" in str(async_params["http_client"].annotation)


def test_lifecycle_methods() -> None:
    for name in SYNC_ONLY:
        assert hasattr(Client, name)
    for name in ASYNC_ONLY:
        assert inspect.iscoroutinefunction(getattr(AsyncClient, name))
