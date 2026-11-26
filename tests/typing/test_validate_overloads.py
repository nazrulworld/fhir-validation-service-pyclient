"""Static checks of ``validate`` overloads (T038). mypy/pyright evaluate ``assert_type``.

At runtime the function is never called (the client would need a server); importing the module
is enough for pytest, and the type checkers do the real work in CI.
"""

from __future__ import annotations

from typing import assert_type

from fvs_client import (
    Client,
    OperationOutcomeResult,
    RawResponse,
    ResultFormat,
    ValidationResult,
)


def _check_types(c: Client) -> None:  # pragma: no cover - type-checked only
    r = {"resourceType": "Patient"}
    assert_type(c.validate(r, fhir_version="R4"), ValidationResult)
    assert_type(
        c.validate(r, fhir_version="R4", result_format=ResultFormat.SUMMARY), ValidationResult
    )
    assert_type(
        c.validate(r, fhir_version="R4", result_format=ResultFormat.OPERATION_OUTCOME_JSON),
        OperationOutcomeResult,
    )
    assert_type(
        c.validate(r, fhir_version="R4", result_format=ResultFormat.OPERATION_OUTCOME_XML),
        OperationOutcomeResult,
    )
    assert_type(c.validate(r, fhir_version="R4", raw=True), RawResponse)
    assert_type(
        c.validate(
            r, fhir_version="R4", raw=True, result_format=ResultFormat.OPERATION_OUTCOME_XML
        ),
        RawResponse,
    )


def test_module_imports() -> None:
    assert callable(_check_types)
