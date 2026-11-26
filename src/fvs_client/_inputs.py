"""Local input checks and resource preparation (nothing is sent when these fail)."""

from __future__ import annotations

import io
import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO
from urllib.parse import urlsplit

import httpx

from fvs_client._bodies import FileBody
from fvs_client._config import check_extra_headers, check_timeout
from fvs_client.errors import InputError
from fvs_client.models import (
    FhirVersion,
    IgInput,
    IgRef,
    ResultFormat,
    TerminologyMode,
    ValidationOptions,
    _render_ig,  # pyright: ignore[reportPrivateUsage]
)

FHIR_JSON = "application/fhir+json"
FHIR_XML = "application/fhir+xml"
_SNIFF_BYTES = 1024
_BOM = b"\xef\xbb\xbf"

Resource = Mapping[str, Any] | str | bytes | os.PathLike[str]


def render_ig(ig: IgInput | None) -> str | None:
    """Render and check the ``ig`` value of a validation request (see ``ValidationOptions``)."""
    return _render_ig(ig)


def _sniff(head: bytes) -> str | None:
    head = head.removeprefix(_BOM).lstrip()
    if head.startswith(b"{"):
        return FHIR_JSON
    if head.startswith(b"<"):
        return FHIR_XML
    return None


def _sniff_or_fail(head: bytes) -> str:
    ctype = _sniff(head)
    if ctype is None:
        raise InputError(
            "The resource is neither JSON (starting with '{') nor XML (starting with '<'); "
            "pass content_type= to send it anyway"
        )
    return ctype


def _prepare_path(path: Path, content_type: str | None) -> tuple[FileBody, str]:
    if not path.is_file():
        raise InputError(f"{path} is not a readable file")
    if content_type:
        return FileBody(path), content_type
    suffix = path.suffix.lower()
    if suffix == ".json":
        return FileBody(path), FHIR_JSON
    if suffix == ".xml":
        return FileBody(path), FHIR_XML
    with path.open("rb") as fh:
        head = fh.read(_SNIFF_BYTES)
    return FileBody(path), _sniff_or_fail(head)


def prepare_resource(resource: Resource, content_type: str | None) -> tuple[bytes | FileBody, str]:
    """Return the request body and its ``Content-Type`` for ``resource``.

    * ``dict`` → compact JSON, ``application/fhir+json``;
    * ``str``/``bytes`` → sent as-is; JSON or XML is detected from the first character;
    * path → streamed from disk; ``.json``/``.xml`` suffix decides, otherwise detected.

    ``content_type`` overrides the detection.

    Raises:
        InputError: unsupported type, unreadable file, or content that is neither JSON nor XML.
    """
    if isinstance(resource, Mapping):
        try:
            body = json.dumps(dict(resource), separators=(",", ":"), ensure_ascii=False).encode()
        except (TypeError, ValueError) as exc:
            raise InputError(f"The resource cannot be encoded as JSON: {exc}") from exc
        return body, content_type or FHIR_JSON
    if isinstance(resource, str):
        body = resource.encode("utf-8")
        return body, content_type or _sniff_or_fail(body[:_SNIFF_BYTES])
    if isinstance(resource, bytes | bytearray):
        body = bytes(resource)
        return body, content_type or _sniff_or_fail(body[:_SNIFF_BYTES])
    if isinstance(resource, os.PathLike):  # pyright: ignore[reportUnnecessaryIsInstance]
        return _prepare_path(Path(os.fspath(resource)), content_type)
    raise InputError(
        f"Unsupported resource type {type(resource).__name__}: pass a dict, str, bytes or path"
    )


def resolve_validation_options(
    options: ValidationOptions | None,
    *,
    ig: IgInput | None,
    profiles: Sequence[str],
    tx: str | None,
    tx_mode: TerminologyMode | str | None,
    result_format: ResultFormat | str,
    content_type: str | None,
) -> ValidationOptions:
    """Return ``options``, or build them from the keyword arguments (never both).

    Raises:
        InputError: ``options`` given together with keyword options, or any rule broken.
    """
    keywords_used = (
        ig is not None
        or bool(tuple(profiles) if not isinstance(profiles, str) else profiles)
        or tx is not None
        or tx_mode is not None
        or result_format != ResultFormat.SUMMARY
        or content_type is not None
    )
    if options is not None:
        if keywords_used:
            raise InputError("Pass either options= or keyword options (ig, profiles, …), not both")
        return options
    return ValidationOptions(
        ig=ig,
        profiles=profiles,
        tx=tx,
        tx_mode=tx_mode,
        result_format=result_format,
        content_type=content_type,
    )


@dataclass(frozen=True, slots=True)
class Batch:
    """Checked settings shared by every resource of ``validate_many``."""

    fhir_version: FhirVersion
    options: ValidationOptions


def prepare_batch(
    concurrency: int,
    fhir_version: FhirVersion | str,
    options: ValidationOptions | None,
    *,
    ig: IgInput | None,
    profiles: Sequence[str],
    tx: str | None,
    tx_mode: TerminologyMode | str | None,
    result_format: ResultFormat | str,
    content_type: str | None,
    timeout: float | httpx.Timeout | None,
    extra_headers: Mapping[str, str] | None,
) -> Batch:
    """Check everything shared by a batch once, before anything is sent.

    Raises:
        InputError: ``concurrency`` < 1, or invalid shared options.
    """
    if isinstance(concurrency, bool) or concurrency < 1:
        raise InputError("concurrency must be at least 1")
    if timeout is not None:
        check_timeout(timeout)
    check_extra_headers(extra_headers)
    opts = resolve_validation_options(
        options,
        ig=ig,
        profiles=profiles,
        tx=tx,
        tx_mode=tx_mode,
        result_format=result_format,
        content_type=content_type,
    )
    return Batch(fhir_version=FhirVersion.parse(fhir_version), options=opts)


# --------------------------------------------------------------------------- administration

_SERIES_RE = re.compile(r"^\d+\.[xX](\.[xX])?$|^\d+\.\d+\.[xX]$")
_MAX_REGISTER_VERSION = 64
_MAX_IG_KEY = 256


def _check_series(ref: IgRef) -> IgRef:
    if ref.is_series and ref.version is not None and not _SERIES_RE.fullmatch(ref.version):
        raise InputError(
            f"Version {ref.version!r} is not a valid series: use N.x, N.x.x or N.N.x (e.g. 1.2.x)"
        )
    return ref


def _refs(ig: IgInput) -> tuple[IgRef, ...]:
    if isinstance(ig, IgRef):
        return (ig,)
    if isinstance(ig, tuple):
        return ig
    if not ig.strip():
        raise InputError("ig must not be empty")
    return tuple(IgRef.parse(p) for p in ig.split("|"))


def check_include_ig(ig: IgInput) -> tuple[IgRef, ...]:
    """IGs of ``contexts.include``: one or two; version exact, ``latest``, ``None`` or a series.

    Raises:
        InputError: more than two IGs, the same package twice, or an invalid series.
    """
    refs = _refs(ig)
    if len(refs) not in (1, 2):
        raise InputError("include takes one IG, or exactly two for a two-IG context")
    if len(refs) == 2 and refs[0].name == refs[1].name:
        raise InputError("The two IGs of a two-IG context must be different packages")
    return tuple(_check_series(r) for r in refs)


def check_exact_ig(ig: IgInput) -> str:
    """The ``ig`` of ``contexts.exclude``/``update``: exact ``name#version`` or a two-IG key.

    Raises:
        InputError: no version, ``latest``, a series, or longer than 256 characters.
    """
    refs = _refs(ig)
    if len(refs) not in (1, 2) or not all(r.is_exact for r in refs):
        raise InputError(
            "ig must be an exact name#version (or name#version|name#version); "
            "'latest' and version series are not allowed here"
        )
    rendered = "|".join(str(r) for r in refs)
    if len(rendered) > _MAX_IG_KEY:
        raise InputError(f"ig must be at most {_MAX_IG_KEY} characters")
    return rendered


def check_register_args(name: str | None, version: str, download_url: str | None) -> None:
    """Rules of ``packages.register``.

    Raises:
        InputError: not exactly one of ``name``/``download_url``, a version over 64 characters
            or an invalid series, or a ``download_url`` that is not an http(s) URL.
    """
    if (name is None) == (download_url is None):
        raise InputError("register needs exactly one of name or download_url")
    if len(version) > _MAX_REGISTER_VERSION:
        raise InputError(f"version must be at most {_MAX_REGISTER_VERSION} characters")
    if name is not None:
        _check_series(IgRef(name, version))
    if download_url is not None:
        parts = urlsplit(download_url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise InputError("download_url must be an absolute http(s) URL")


def prepare_archive(archive: os.PathLike[str] | BinaryIO) -> tuple[str, BinaryIO, bool]:
    """Return ``(filename, binary handle, should_close)`` for streaming an IG archive.

    Raises:
        InputError: the file does not exist, or ``archive`` is a text-mode handle.
    """
    if isinstance(archive, os.PathLike):
        path = Path(os.fspath(archive))
        if not path.is_file():
            raise InputError(f"{path} is not a readable file")
        return path.name, path.open("rb"), True
    mode = getattr(archive, "mode", "rb")
    if isinstance(archive, io.TextIOBase) or (isinstance(mode, str) and "b" not in mode):
        raise InputError("archive must be a path or a file opened in binary mode ('rb')")
    name = getattr(archive, "name", None)
    filename = Path(name).name if isinstance(name, str) and name else "package.tgz"
    return filename, archive, False
