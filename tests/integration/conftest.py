"""Fixtures for tests against a live FHIR Validation Service (T020).

Every test module in this package sets ``pytestmark = pytest.mark.integration`` (so the default
``-m 'not integration'`` deselects it) and is skipped unless ``FVS_IT_BASE_URL`` is set. Keys come
from ``FVS_IT_API_KEY`` (VALIDATE role) and ``FVS_IT_ADMIN_API_KEY`` (ADMIN role).
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from fvs_client import Client


@pytest.fixture(scope="session")
def it_base_url() -> str:
    url = os.environ.get("FVS_IT_BASE_URL")
    if not url:
        pytest.skip("FVS_IT_BASE_URL is not set; integration tests need a running service")
    return url


@pytest.fixture
def it_client(it_base_url: str) -> Iterator[Client]:
    from fvs_client import Client

    with Client(it_base_url, api_key=os.environ.get("FVS_IT_API_KEY") or None) as c:
        yield c


@pytest.fixture
def it_admin_client(it_base_url: str) -> Iterator[Client]:
    from fvs_client import Client

    key = os.environ.get("FVS_IT_ADMIN_API_KEY")
    if not key:
        pytest.skip("FVS_IT_ADMIN_API_KEY is not set")
    with Client(it_base_url, api_key=key) as c:
        yield c
