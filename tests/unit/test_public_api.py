"""The public surface matches contracts/public-api.md and is fully documented (T053)."""

from __future__ import annotations

import enum
import inspect
import re

import fvs_client

# contracts/public-api.md#top-level-exports-fvs_client__all__
CONTRACT_EXPORTS = {
    # clients and configuration
    "Client",
    "AsyncClient",
    "RetryConfig",
    "__version__",
    "SUPPORTED_API",
    # enums
    "FhirVersion",
    "Severity",
    "TerminologyMode",
    "TxSource",
    "HealthStatus",
    "ResultFormat",
    "RateLimitScope",
    "ProblemType",
    # inputs
    "IgRef",
    "ValidationOptions",
    "TerminologySettings",
    "AccessChange",
    # results
    "ValidationResult",
    "ValidationIssue",
    "OperationOutcomeResult",
    "ValidationContextInfo",
    "ResponseMeta",
    "RateLimitInfo",
    "RawResponse",
    "IncludeResult",
    "IncludedIg",
    "ExcludeResult",
    "ContextAccessResult",
    "IgPackageResult",
    "PackageAccessResult",
    "PackageDependencies",
    "PackageFiles",
    "HealthReport",
    "ReadinessReport",
    "LivenessReport",
    "Problem",
    # errors
    "FVSError",
    "InputError",
    "TransportError",
    "FVSConnectionError",
    "FVSTimeoutError",
    "APIError",
    "BadRequestError",
    "InvalidResourceError",
    "UnknownProfileError",
    "DependencyConflictError",
    "AuthenticationError",
    "PermissionDeniedError",
    "NotFoundError",
    "ConflictError",
    "RateLimitError",
    "ServiceUnavailableError",
    "ServerError",
}

# Symbols delivered by later user stories (emptied as US3, US4 and US5 landed).
PENDING: set[str] = set()

CLIENT_CLASSES = {"Client", "AsyncClient"}


def test_all_matches_contract() -> None:
    assert set(fvs_client.__all__) == CONTRACT_EXPORTS - PENDING
    assert len(fvs_client.__all__) == len(set(fvs_client.__all__))


def test_every_export_resolves() -> None:
    for name in fvs_client.__all__:
        assert hasattr(fvs_client, name), name


def _public_objects() -> list[tuple[str, object]]:
    return [
        (n, getattr(fvs_client, n))
        for n in fvs_client.__all__
        if n not in ("__version__", "SUPPORTED_API")
    ]


def test_every_export_has_a_docstring() -> None:
    missing = [n for n, obj in _public_objects() if not (inspect.getdoc(obj) or "").strip()]
    assert missing == []


def _sub_client_classes() -> list[type]:
    """Classes behind ``client.contexts`` / ``.packages`` / ``.health`` (property annotations)."""
    classes: list[type] = []
    for name in CLIENT_CLASSES - PENDING:
        cls = getattr(fvs_client, name)
        for attr in ("contexts", "packages", "health"):
            member = getattr(cls, attr, None)
            if isinstance(member, property) and member.fget is not None:
                ret = inspect.signature(member.fget, eval_str=True).return_annotation
                if isinstance(ret, type):
                    classes.append(ret)
    return classes


def test_every_public_method_and_property_has_a_docstring() -> None:
    missing: list[str] = []
    classes = [obj for _, obj in _public_objects() if isinstance(obj, type)]
    for cls in [*classes, *_sub_client_classes()]:
        for attr, value in vars(cls).items():
            if attr.startswith("_"):
                continue
            if isinstance(cls, enum.EnumMeta) and attr in cls.__members__:
                continue  # enum members document themselves through the enum
            func = value.fget if isinstance(value, property) else value
            if isinstance(func, classmethod | staticmethod):
                func = func.__func__
            if not callable(func):
                continue
            if not (inspect.getdoc(func) or "").strip():
                missing.append(f"{cls.__name__}.{attr}")
    assert missing == []


def test_version_is_pep440() -> None:
    assert re.fullmatch(
        r"\d+(\.\d+)*((a|b|rc)\d+)?(\.post\d+)?(\.dev\d+)?(\+[\w.]+)?", fvs_client.__version__
    )


def test_supported_api() -> None:
    assert fvs_client.SUPPORTED_API == "1.0"


def test_exports_live_in_public_modules() -> None:
    private = [
        n
        for n, obj in _public_objects()
        if n not in CLIENT_CLASSES
        and getattr(obj, "__module__", "fvs_client").startswith("fvs_client._")
    ]
    assert private == []
