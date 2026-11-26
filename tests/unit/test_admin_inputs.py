"""Local checks for administrative operations (T068)."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from fvs_client import AccessChange, IgRef, InputError, TerminologySettings
from fvs_client._inputs import (
    check_exact_ig,
    check_include_ig,
    check_register_args,
    prepare_archive,
)

# --------------------------------------------------------------------------- AccessChange
# "at least one field must be set"; owner "^[A-Za-z0-9_-]{2,32}$"


def test_access_change_needs_a_field() -> None:
    with pytest.raises(InputError, match="at least one"):
        AccessChange()


@pytest.mark.parametrize("owner", ["ab", "acme_org-1", "A" * 32])
def test_access_change_valid_owner(owner: str) -> None:
    assert AccessChange(owner=owner).owner == owner


@pytest.mark.parametrize("owner", ["a", "A" * 33, "acme org", "acme.org", "ac/me", ""])
def test_access_change_invalid_owner(owner: str) -> None:
    with pytest.raises(InputError, match="owner"):
        AccessChange(owner=owner)


def test_access_change_to_wire_only_set_fields() -> None:
    assert AccessChange(shareable=False).to_wire() == {"shareable": False}
    change = AccessChange(owner="acme", terminology=TerminologySettings(mode="none"))
    assert change.to_wire() == {"owner": "acme", "terminology": {"mode": "none"}}


# --------------------------------------------------------------------------- include
# exact version, `latest` or a series N.x / N.x.x / N.N.x; two-IG tuple, no repeated id


@pytest.mark.parametrize(
    ("ig", "expected"),
    [
        ("hl7.fhir.uv.ips", [("hl7.fhir.uv.ips", None)]),
        ("hl7.fhir.uv.ips#1.1.0", [("hl7.fhir.uv.ips", "1.1.0")]),
        ("hl7.fhir.uv.ips#latest", [("hl7.fhir.uv.ips", "latest")]),
        (IgRef("a", "1.x"), [("a", "1.x")]),
        (IgRef("a", "1.x.x"), [("a", "1.x.x")]),
        (IgRef("a", "1.2.x"), [("a", "1.2.x")]),
        ((IgRef("a", "1.0.0"), IgRef("b")), [("a", "1.0.0"), ("b", None)]),
        ("a#1.0.0|b#2.x", [("a", "1.0.0"), ("b", "2.x")]),
    ],
)
def test_include_ig_forms(
    ig: str | IgRef | tuple[IgRef, IgRef], expected: list[tuple[str, str | None]]
) -> None:
    assert [(r.name, r.version) for r in check_include_ig(ig)] == expected


@pytest.mark.parametrize(
    "ig",
    [
        "a#x.1",
        "a#1.x.2",
        "a#1.2.3.x",
        "a#x",
        (IgRef("a", "1.0.0"), IgRef("a", "2.0.0")),
        "a#1|a#2",
        "a#1|b#2|c#3",
    ],
)
def test_include_ig_rejects(ig: str | IgRef | tuple[IgRef, IgRef]) -> None:
    with pytest.raises(InputError):
        check_include_ig(ig)


# --------------------------------------------------------------------------- exclude / update
# exact name#version or a two-IG key: no `latest`, no series


@pytest.mark.parametrize(
    ("ig", "rendered"),
    [
        ("a.ig#1.0.0", "a.ig#1.0.0"),
        (IgRef("a.ig", "1.0.0"), "a.ig#1.0.0"),
        ("a#1.0.0|b#2.0.0", "a#1.0.0|b#2.0.0"),
        ((IgRef("a", "1.0.0"), IgRef("b", "2.0.0")), "a#1.0.0|b#2.0.0"),
    ],
)
def test_exact_ig(ig: str | IgRef | tuple[IgRef, IgRef], rendered: str) -> None:
    assert check_exact_ig(ig) == rendered


@pytest.mark.parametrize(
    "ig", ["a.ig", "a.ig#latest", "a.ig#1.x", "a#1.0.0|b", "x" * 250 + "#1.0.0.0"]
)
def test_exact_ig_rejects(ig: str) -> None:
    with pytest.raises(InputError):
        check_exact_ig(ig)


# --------------------------------------------------------------------------- register
# exactly one of name / download_url; version ≤ 64 chars


def test_register_needs_exactly_one_source() -> None:
    with pytest.raises(InputError, match="exactly one"):
        check_register_args(None, "latest", None)
    with pytest.raises(InputError, match="exactly one"):
        check_register_args("a.ig", "latest", "https://example.org/a.tgz")


def test_register_version_rules() -> None:
    check_register_args("a.ig", "v" * 64, None)
    with pytest.raises(InputError, match="64"):
        check_register_args("a.ig", "v" * 65, None)
    check_register_args("a.ig", "1.2.x", None)
    with pytest.raises(InputError):
        check_register_args("a.ig", "1.x.2", None)
    with pytest.raises(InputError):
        check_register_args("a b", "latest", None)


@pytest.mark.parametrize("url", ["ftp://example.org/a.tgz", "not a url", "https://"])
def test_register_download_url_must_be_http(url: str) -> None:
    with pytest.raises(InputError, match="download_url"):
        check_register_args(None, "latest", url)


# --------------------------------------------------------------------------- upload


def test_archive_from_path(tmp_path: Path) -> None:
    path = tmp_path / "pkg.tgz"
    path.write_bytes(b"\x1f\x8b" + b"x" * 10)
    name, handle, should_close = prepare_archive(path)
    try:
        assert name == "pkg.tgz"
        assert should_close is True
        assert handle.read(2) == b"\x1f\x8b"
    finally:
        handle.close()


def test_archive_from_binary_handle(tmp_path: Path) -> None:
    path = tmp_path / "pkg.tgz"
    path.write_bytes(b"\x1f\x8b")
    with path.open("rb") as fh:
        name, handle, should_close = prepare_archive(fh)
        assert (name, handle, should_close) == ("pkg.tgz", fh, False)
    name, handle, _ = prepare_archive(io.BytesIO(b"x"))
    assert name == "package.tgz"


def test_archive_text_handle_rejected(tmp_path: Path) -> None:
    path = tmp_path / "pkg.tgz"
    path.write_text("x")
    with path.open("r") as fh, pytest.raises(InputError, match="binary"):
        prepare_archive(fh)  # type: ignore[arg-type]
    with pytest.raises(InputError, match="binary"):
        prepare_archive(io.StringIO("x"))  # type: ignore[arg-type]


def test_archive_missing_file(tmp_path: Path) -> None:
    with pytest.raises(InputError):
        prepare_archive(tmp_path / "nope.tgz")
