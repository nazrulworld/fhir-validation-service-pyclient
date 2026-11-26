"""Property-based checks (T092)."""

from __future__ import annotations

import string

from hypothesis import given
from hypothesis import strategies as st

from fvs_client import IgRef, InputError, ValidationOptions
from fvs_client._problems import short_name

TOKEN = st.text(alphabet=string.ascii_letters + string.digits + ".-_", min_size=1, max_size=40)
VERSION = st.one_of(
    st.none(), st.just("latest"), st.from_regex(r"\d{1,3}\.\d{1,3}\.\d{1,3}", fullmatch=True)
)
SLUG = st.from_regex(r"[a-z][a-z-]{0,30}[a-z]", fullmatch=True)
HOST = st.from_regex(r"[a-z]{1,10}\.[a-z]{2,5}", fullmatch=True)


@given(name=TOKEN, version=VERSION)
def test_igref_round_trip(name: str, version: str | None) -> None:
    ref = IgRef(name, version)
    assert IgRef.parse(str(ref)) == ref


@given(host=HOST, prefix=st.lists(SLUG, max_size=3), slug=SLUG, trailing=st.booleans())
def test_short_name_of_any_problem_uri(
    host: str, prefix: list[str], slug: str, trailing: bool
) -> None:
    uri = (
        f"https://{host}/"
        + "".join(f"{p}/" for p in prefix)
        + f"problems/{slug}"
        + ("/" if trailing else "")
    )
    assert short_name(uri) == slug


@given(st.lists(st.integers(min_value=0, max_value=40), max_size=40))
def test_never_more_than_ten_distinct_profiles(ids: list[int]) -> None:
    profiles = [f"http://example.org/StructureDefinition/P{i}" for i in ids]
    distinct = len(set(profiles))
    try:
        opts = ValidationOptions(profiles=profiles)
    except InputError:
        assert distinct > 10
    else:
        assert distinct <= 10
        assert len(tuple(opts.profiles)) == distinct
