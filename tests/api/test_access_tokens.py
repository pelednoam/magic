"""The token on the wire: the header a request carries, and whether it matches.

The wire half. `test_tokenfile` covers where the token comes from.
"""

from __future__ import annotations

import pytest

from mtgcoach.api.access import SCHEME, allowed, presented


def test_a_header_in_the_agreed_shape_is_read() -> None:
    assert presented(f"{SCHEME}abc", None) == "abc"


@pytest.mark.parametrize("header", ["abc", "Basic abc", "", None])
def test_a_header_in_any_other_shape_is_not(header: str | None) -> None:
    assert presented(header, None) == ""


def test_the_query_string_is_the_fallback() -> None:
    assert presented(None, "abc") == "abc"
    assert presented(f"{SCHEME}header-wins", "query") == "header-wins"


def test_an_empty_token_is_never_allowed() -> None:
    """`compare_digest("", "")` is true.

    An unconfigured server must not accept an unconfigured client.
    """
    assert not allowed("", "")
    assert not allowed("", "real")


def test_a_non_ascii_token_is_refused_rather_than_raising() -> None:
    """`compare_digest` refuses two non-ASCII `str`s with a TypeError.

    So `?token=%FF` -- which `parse_qs` decodes to U+FFFD -- turned an
    unauthenticated request into a 500 from inside the gatekeeper.
    """
    assert not allowed("�", "real")
    assert not allowed("�", "�" + "x")


def test_a_token_that_really_is_non_ascii_still_matches_itself() -> None:
    """Nothing generates one, but refusing to compare it would be its own bug.

    Bytes have no ASCII restriction, so there is nothing to give up here.
    """
    assert allowed("café", "café")


@pytest.mark.parametrize("scheme", ["Bearer", "bearer", "BEARER", "BeArEr"])
def test_the_scheme_name_is_case_insensitive(scheme: str) -> None:
    """RFC 7235 §2.1, and several clients and proxies lowercase it.

    Getting this wrong is a 401 that reads as "wrong token" to somebody
    holding the right one.
    """
    assert presented(f"{scheme} abc", None) == "abc"
