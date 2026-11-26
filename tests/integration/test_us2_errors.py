"""US2 against a live FHIR Validation Service 1.0 (quickstart §5) (T047)."""

from __future__ import annotations

import pytest

from fvs_client import (
    AuthenticationError,
    Client,
    FVSConnectionError,
    InputError,
    NotFoundError,
    ProblemType,
    UnknownProfileError,
)

pytestmark = pytest.mark.integration

PATIENT = {"resourceType": "Patient"}


def test_wrong_key_is_authentication_error(it_base_url: str) -> None:
    with (
        Client(it_base_url, api_key="definitely-not-a-valid-key") as c,
        pytest.raises(AuthenticationError) as info,
    ):
        c.validate(PATIENT, fhir_version="R4")
    assert info.value.status_code == 401
    assert info.value.request_id


def test_unknown_profile(it_client: Client) -> None:
    with pytest.raises(UnknownProfileError) as info:
        it_client.validate(PATIENT, fhir_version="R4", profiles=["http://example.org/nope"])
    assert info.value.unresolved_profiles == ("http://example.org/nope",)


def test_package_not_found(it_client: Client) -> None:
    with pytest.raises(NotFoundError) as info:
        it_client.validate(PATIENT, fhir_version="R4", ig="no.such.ig#1.0.0")
    assert info.value.problem_type == ProblemType.PACKAGE_NOT_FOUND


def test_local_checks_send_nothing(it_client: Client) -> None:
    with pytest.raises(InputError):
        it_client.validate(PATIENT, fhir_version="R6")
    with pytest.raises(InputError):
        it_client.validate(
            PATIENT, fhir_version="R4", profiles=[f"http://p/{i}" for i in range(11)]
        )


def test_unreachable_service_is_connection_error() -> None:
    with Client("http://127.0.0.1:1", retries=0) as c, pytest.raises(FVSConnectionError):
        c.validate(PATIENT, fhir_version="R4")
