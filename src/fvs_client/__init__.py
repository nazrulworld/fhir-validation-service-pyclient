"""Typed Python SDK (sync + async) for the FHIR Validation Service HTTP API.

Quick start::

    from fvs_client import Client

    with Client("https://fvs.example.org", api_key="…") as fvs:
        result = fvs.validate({"resourceType": "Patient"}, fhir_version="R4")
        print(result.valid, [i.message for i in result.errors])

See https://github.com/nazrulworld/fhir-validation-service for the service itself.
"""

from __future__ import annotations

try:
    from fvs_client._version import __version__
except ImportError:  # pragma: no cover - only when running from a source tree without a build
    __version__ = "0.0.0"

from fvs_client._async.client import AsyncClient
from fvs_client._sync.client import Client
from fvs_client.errors import (
    APIError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    DependencyConflictError,
    FVSConnectionError,
    FVSError,
    FVSTimeoutError,
    InputError,
    InvalidResourceError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ServerError,
    ServiceUnavailableError,
    TransportError,
    UnknownProfileError,
)
from fvs_client.models import (
    AccessChange,
    ContextAccessResult,
    ExcludeResult,
    FhirVersion,
    HealthReport,
    HealthStatus,
    IgPackageResult,
    IgRef,
    IncludedIg,
    IncludeResult,
    LivenessReport,
    OperationOutcomeResult,
    PackageAccessResult,
    PackageDependencies,
    PackageFiles,
    Problem,
    ProblemType,
    RateLimitInfo,
    RateLimitScope,
    RawResponse,
    ReadinessReport,
    ResponseMeta,
    ResultFormat,
    RetryConfig,
    Severity,
    TerminologyMode,
    TerminologySettings,
    TxSource,
    ValidationContextInfo,
    ValidationIssue,
    ValidationOptions,
    ValidationResult,
)

SUPPORTED_API = "1.0"
"""FHIR Validation Service API version (major.minor) this release supports."""

__all__ = [
    "SUPPORTED_API",
    "APIError",
    "AccessChange",
    "AsyncClient",
    "AuthenticationError",
    "BadRequestError",
    "Client",
    "ConflictError",
    "ContextAccessResult",
    "DependencyConflictError",
    "ExcludeResult",
    "FVSConnectionError",
    "FVSError",
    "FVSTimeoutError",
    "FhirVersion",
    "HealthReport",
    "HealthStatus",
    "IgPackageResult",
    "IgRef",
    "IncludeResult",
    "IncludedIg",
    "InputError",
    "InvalidResourceError",
    "LivenessReport",
    "NotFoundError",
    "OperationOutcomeResult",
    "PackageAccessResult",
    "PackageDependencies",
    "PackageFiles",
    "PermissionDeniedError",
    "Problem",
    "ProblemType",
    "RateLimitError",
    "RateLimitInfo",
    "RateLimitScope",
    "RawResponse",
    "ReadinessReport",
    "ResponseMeta",
    "ResultFormat",
    "RetryConfig",
    "ServerError",
    "ServiceUnavailableError",
    "Severity",
    "TerminologyMode",
    "TerminologySettings",
    "TransportError",
    "TxSource",
    "UnknownProfileError",
    "ValidationContextInfo",
    "ValidationIssue",
    "ValidationOptions",
    "ValidationResult",
    "__version__",
]
