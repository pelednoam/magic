"""The token itself: making one, keeping it, and reading one off a request.

No server here. What is tested is the value and the file it lives in -- the
door it opens is ``test_access``.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from mtgcoach.api.access import SCHEME, allowed, new_token, presented, token_at

if TYPE_CHECKING:
    from pathlib import Path


def test_a_fresh_token_is_not_guessable() -> None:
    assert len(new_token()) >= 32
    assert new_token() != new_token()


def test_a_token_file_is_made_once_and_read_back(tmp_path: Path) -> None:
    """Restarting the server must not invalidate the phone in somebody's hand."""
    where = tmp_path / "token"
    first = token_at(where)
    assert token_at(where) == first


def test_a_token_file_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    """Created with the permissions it needs, not fixed afterwards.

    A token that was briefly world-readable was world-readable.
    """
    where = tmp_path / "token"
    token_at(where)
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_a_directory_that_does_not_exist_yet_is_made(tmp_path: Path) -> None:
    assert token_at(tmp_path / "nested" / "token")


def test_an_empty_token_file_is_replaced(tmp_path: Path) -> None:
    """A truncated write should not leave the server with no access control."""
    where = tmp_path / "token"
    where.write_text("   \n", encoding="utf-8")
    assert token_at(where).strip()


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
