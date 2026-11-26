"""Parsing of administrative and package responses (T070)."""

from __future__ import annotations

import json

from fvs_client import (
    ContextAccessResult,
    ExcludeResult,
    IgPackageResult,
    IncludedIg,
    IncludeResult,
    PackageAccessResult,
    PackageDependencies,
    PackageFiles,
    TerminologyMode,
)
from fvs_client._parsing import (
    build_meta,
    build_raw,
    parse_context_access,
    parse_dependencies,
    parse_exclude,
    parse_files,
    parse_ig_package,
    parse_include,
    parse_package_access,
)
from fvs_client.models import RawResponse
from tests.fixtures import load, load_json


def _raw(path: str) -> RawResponse:
    h = {"content-type": "application/json", "x-request-id": "r-1"}
    return build_raw(200, h, load(path), build_meta(200, h, 0.0, 1))


def test_include_single() -> None:
    r = parse_include(_raw("admin/include_single.json"))
    assert isinstance(r, IncludeResult)
    assert r.fhir_version == "R4"
    assert r.key == "hl7.fhir.uv.ips#1.1.0"
    assert r.ig_packages == (
        IncludedIg(ig_package_id="hl7.fhir.uv.ips", ig_package_version="1.1.0"),
    )
    assert r.aliases == ()
    assert r.requested_version == "1.1.x"
    assert r.revision == 42
    assert r.included == ("hl7.fhir.uv.ips#1.1.0",)
    assert r.resolved[0] == "hl7.fhir.uv.ips#1.1.0"
    assert r.terminology is not None
    assert r.terminology.mode is TerminologyMode.SERVER
    assert r.terminology.server == "https://tx.fhir.org/r4"
    assert (r.owner, r.shareable, r.warnings) == ("acme", True, ())
    assert r.meta.request_id == "r-1"
    assert r.raw == load_json("admin/include_single.json")


def test_include_two() -> None:
    r = parse_include(_raw("admin/include_two.json"))
    assert r.key == "a.ig#1.0.0|b.ig#2.0.0"
    assert [i.requested_version for i in r.ig_packages] == ["1.0.0", "latest"]
    assert r.aliases == ("b.ig#2.0.0|a.ig#1.0.0", "a.ig#1.0.0")
    assert r.requested_version is None
    assert r.terminology is not None
    assert r.terminology.mode is TerminologyMode.NONE
    assert r.shareable is False
    assert len(r.warnings) == 1


def test_exclude() -> None:
    r = parse_exclude(_raw("admin/exclude.json"))
    assert isinstance(r, ExcludeResult)
    assert (r.fhir_version, r.revision, r.excluded, r.included, r.warnings) == (
        "R4",
        44,
        "hl7.fhir.uv.ips#1.1.0",
        (),
        (),
    )


def test_context_access() -> None:
    r = parse_context_access(_raw("admin/context_access.json"))
    assert isinstance(r, ContextAccessResult)
    assert (r.fhir_version, r.ig_package, r.revision, r.owner, r.shareable) == (
        "R4",
        "hl7.fhir.uv.ips#1.1.0",
        45,
        "acme",
        True,
    )
    assert r.terminology is not None


def test_ig_package() -> None:
    r = parse_ig_package(_raw("admin/ig_registration.json"))
    assert isinstance(r, IgPackageResult)
    assert (r.name, r.version, r.requested_version, r.downloaded, r.owner, r.shareable) == (
        "hl7.fhir.uv.ips",
        "1.1.0",
        "latest",
        True,
        "acme",
        True,
    )


def test_package_access() -> None:
    r = parse_package_access(_raw("admin/ig_access.json"))
    assert isinstance(r, PackageAccessResult)
    assert (r.name, r.version, r.owner, r.shareable, r.warnings) == (
        "hl7.fhir.uv.ips",
        "1.1.0",
        "acme",
        False,
        (),
    )


def test_dependencies_and_files() -> None:
    d = parse_dependencies(_raw("admin/dependencies.json"))
    assert isinstance(d, PackageDependencies)
    assert d.dependencies == ("hl7.fhir.r4.core#4.0.1", "hl7.terminology.r4#5.0.0")
    f = parse_files(_raw("admin/files.json"))
    assert isinstance(f, PackageFiles)
    assert f.files[0] == "package/package.json"


def test_to_dict_and_missing_fields() -> None:
    h = {"content-type": "application/json"}
    raw = build_raw(200, h, b'{"status":"success"}', build_meta(200, h, 0.0, 1))
    r = parse_include(raw)
    assert (r.key, r.ig_packages, r.terminology, r.owner) == ("", (), None, None)
    d = parse_include(_raw("admin/include_two.json")).to_dict()
    assert d["ig_packages"][1]["requested_version"] == "latest"
    assert d["terminology"] == {"mode": "none", "server": None}
    json.dumps(d)
