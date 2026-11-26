"""Validation option rules from data-model.md (T032)."""

from __future__ import annotations

import pytest

from fvs_client import (
    IgRef,
    InputError,
    ResultFormat,
    TerminologyMode,
    TerminologySettings,
    ValidationOptions,
)
from fvs_client._inputs import render_ig

# --------------------------------------------------------------------------- IgRef
# "`name` non-empty; no `#`, `|`, `/` or whitespace"
# "`version` `None` / `"latest"` / exact version"


@pytest.mark.parametrize(
    "text", ["hl7.fhir.us.core#6.1.0", "a.b", "a.b#latest", "x_y-z#1.0.0-ballot"]
)
def test_igref_round_trip(text: str) -> None:
    assert str(IgRef.parse(text)) == text


def test_igref_parse_fields() -> None:
    assert IgRef.parse("a.b#1.0.0") == IgRef("a.b", "1.0.0")
    assert IgRef.parse("a.b") == IgRef("a.b")
    assert IgRef("a.b").version is None


@pytest.mark.parametrize("name", ["", " ", "a#b", "a|b", "a/b", "a b", "a\tb"])
def test_igref_bad_names(name: str) -> None:
    with pytest.raises(InputError, match="IG package name"):
        IgRef(name, "1.0.0")


@pytest.mark.parametrize("version", ["", "1.0 .0", "1#0", "1|0", "1/0"])
def test_igref_bad_versions(version: str) -> None:
    with pytest.raises(InputError, match="IG package version"):
        IgRef("a.b", version)


@pytest.mark.parametrize(
    ("version", "exact", "series"),
    [
        ("1.0.0", True, False),
        (None, False, False),
        ("latest", False, False),
        ("1.2.x", False, True),
        ("1.x", False, True),
        ("1.X.X", False, True),
    ],
)
def test_igref_version_kinds(version: str | None, exact: bool, series: bool) -> None:
    ref = IgRef("a.b", version)
    assert ref.is_exact is exact
    assert ref.is_series is series


# --------------------------------------------------------------------------- ig on validate
# "Rendered string ≤ 256 chars; a two-IG form needs exact versions in both parts;
#  version series (`1.2.x`) rejected"


def test_render_ig_forms() -> None:
    assert render_ig(None) is None
    assert render_ig("a.b#1.0.0") == "a.b#1.0.0"
    assert render_ig(IgRef("a.b")) == "a.b"
    assert render_ig((IgRef("a", "1.0.0"), IgRef("b", "2.0.0"))) == "a#1.0.0|b#2.0.0"
    assert render_ig("a#1.0.0|b#2.0.0") == "a#1.0.0|b#2.0.0"


@pytest.mark.parametrize(
    "ig",
    [
        "a#1.0.0|b",
        "a|b#2.0.0",
        "a#latest|b#2.0.0",
        "a#1.0.0|b#2.0.0|c#3.0.0",
        (IgRef("a", "1.0.0"), IgRef("b")),
        "a#1.2.x",
        IgRef("a", "1.x"),
        "x" * 257,
        "",
    ],
)
def test_render_ig_rejects(ig: str | IgRef | tuple[IgRef, IgRef]) -> None:
    with pytest.raises(InputError):
        render_ig(ig)


def test_render_ig_max_length_is_256() -> None:
    name = "n" * 250
    assert render_ig(f"{name}#1.0.0") == f"{name}#1.0.0"  # 256 chars
    with pytest.raises(InputError, match="256"):
        render_ig(f"{name}#1.0.00")


# --------------------------------------------------------------------------- profiles
# "≤ 10 distinct after trim/dedupe (order preserved); each ≤ 1024 chars; no empty items"


def test_profiles_trimmed_and_deduplicated_in_order() -> None:
    opts = ValidationOptions(profiles=[" http://a ", "http://b", "http://a"])
    assert opts.profiles == ("http://a", "http://b")


def test_ten_distinct_profiles_allowed_with_duplicates() -> None:
    profiles = [f"http://p/{i}" for i in range(10)] * 2
    assert len(ValidationOptions(profiles=profiles).profiles) == 10


def test_eleven_distinct_profiles_rejected() -> None:
    with pytest.raises(InputError, match="10"):
        ValidationOptions(profiles=[f"http://p/{i}" for i in range(11)])


def test_profile_length_limit() -> None:
    ok = "http://p/" + "x" * (1024 - 9)
    assert ValidationOptions(profiles=[ok]).profiles == (ok,)
    with pytest.raises(InputError, match="1024"):
        ValidationOptions(profiles=[ok + "x"])


@pytest.mark.parametrize("bad", ["", "   "])
def test_empty_profile_rejected(bad: str) -> None:
    with pytest.raises(InputError, match="empty"):
        ValidationOptions(profiles=["http://a", bad])


def test_profiles_given_as_single_string_rejected() -> None:
    with pytest.raises(InputError, match="sequence"):
        ValidationOptions(profiles="http://a")


# --------------------------------------------------------------------------- tx / tx_mode
# tx: "≤ 512 chars; `http`/`https` scheme; no query, fragment or user info"
# tx_mode: "one of the 3 values; `tx` together with `none` is rejected"


@pytest.mark.parametrize("tx", ["https://tx.fhir.org/r4", "http://localhost:8080/fhir"])
def test_valid_tx(tx: str) -> None:
    assert ValidationOptions(tx=tx).tx == tx


@pytest.mark.parametrize(
    "tx",
    [
        "ftp://tx.example",
        "tx.example/r4",
        "https://tx.example/r4?x=1",
        "https://tx.example/r4#frag",
        "https://user:pw@tx.example/r4",
        "https://",
        "",
        "https://tx.example/" + "x" * 500,
    ],
)
def test_invalid_tx(tx: str) -> None:
    with pytest.raises(InputError, match="tx"):
        ValidationOptions(tx=tx)


def test_tx_length_limit_is_512() -> None:
    base = "https://tx.example/"
    ok = base + "x" * (512 - len(base))
    assert ValidationOptions(tx=ok).tx == ok
    with pytest.raises(InputError, match="512"):
        ValidationOptions(tx=ok + "x")


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("none", TerminologyMode.NONE),
        ("Server", TerminologyMode.SERVER),
        (TerminologyMode.ECOSYSTEM, TerminologyMode.ECOSYSTEM),
    ],
)
def test_tx_mode_values(value: str, expected: TerminologyMode) -> None:
    assert ValidationOptions(tx_mode=value).tx_mode is expected


def test_unknown_tx_mode_rejected() -> None:
    with pytest.raises(InputError, match="tx_mode"):
        ValidationOptions(tx_mode="offline")


def test_tx_with_mode_none_rejected() -> None:
    with pytest.raises(InputError, match="none"):
        ValidationOptions(tx="https://tx.fhir.org/r4", tx_mode="none")


def test_result_format_from_string() -> None:
    assert ValidationOptions(result_format="operation_outcome_xml").result_format is (
        ResultFormat.OPERATION_OUTCOME_XML
    )
    with pytest.raises(InputError, match="result_format"):
        ValidationOptions(result_format="html")


def test_ig_checked_on_options() -> None:
    with pytest.raises(InputError):
        ValidationOptions(ig="a#1.2.x")
    assert ValidationOptions(ig=IgRef("a", "1.0.0")).ig == "a#1.0.0"


# --------------------------------------------------------------------------- TerminologySettings
# "`server` required when `mode=server`; forbidden when `mode=none`; ≤ 512 chars"


def test_terminology_settings_rules() -> None:
    assert TerminologySettings(mode="none").server is None
    assert TerminologySettings(mode="ecosystem").server is None
    s = TerminologySettings(mode="server", server="https://tx.fhir.org/r4")
    assert s.mode is TerminologyMode.SERVER
    with pytest.raises(InputError, match="required"):
        TerminologySettings(mode="server")
    with pytest.raises(InputError, match="none"):
        TerminologySettings(mode="none", server="https://tx.fhir.org/r4")
    with pytest.raises(InputError, match="512"):
        TerminologySettings(mode="server", server="https://tx.example/" + "x" * 600)
    with pytest.raises(InputError):
        TerminologySettings(mode="server", server="https://tx.example/?q=1")


def test_terminology_settings_to_wire() -> None:
    assert TerminologySettings(mode="none").to_wire() == {"mode": "none"}
    assert TerminologySettings(mode="server", server="https://tx.fhir.org/r4").to_wire() == {
        "mode": "server",
        "server": "https://tx.fhir.org/r4",
    }
