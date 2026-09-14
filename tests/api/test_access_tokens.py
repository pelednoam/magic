"""The token itself: making one, keeping it, and reading one off a request.

No server here. What is tested is the value and the file it lives in -- the
door it opens is ``test_access``.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from mtgcoach.api.access import (
    SCHEME,
    TokenPathError,
    allowed,
    new_token,
    presented,
    token_at,
)

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


def test_an_existing_loose_file_is_tightened(tmp_path: Path) -> None:
    """It can arrive from a git checkout, a backup, or a loose umask.

    The `open` mode is ignored by the kernel for a file that already exists, so
    the first version wrote a fresh token into somebody else's 0644 file and
    left it 0644.
    """
    where = tmp_path / "token"
    where.write_text("already-here\n", encoding="utf-8")
    where.chmod(0o644)
    assert token_at(where) == "already-here"
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_a_symlink_is_not_followed(tmp_path: Path) -> None:
    """A symlink is not a token file.

    One planted at `data/token` would otherwise have this write a token
    wherever it pointed, and read one somebody else chose.
    """
    elsewhere = tmp_path / "elsewhere"
    elsewhere.write_text("planted\n", encoding="utf-8")
    link = tmp_path / "token"
    link.symlink_to(elsewhere)
    with pytest.raises(TokenPathError, match="is a symlink"):
        token_at(link)
    assert elsewhere.read_text(encoding="utf-8") == "planted\n", "the target is untouched"


def test_a_second_server_reads_what_the_first_wrote(tmp_path: Path) -> None:
    """`O_EXCL` settles the race: one creates, the other reads.

    Without it both wrote different tokens over each other and a running app
    was guarded by one while the operator was shown the other.
    """
    where = tmp_path / "token"
    first = token_at(where)
    assert token_at(where) == first


def test_an_empty_file_is_written_over_rather_than_looped_on(tmp_path: Path) -> None:
    """The exclusive create says the file is there; the read says it is empty.

    The first version retried until one of those changed, which was never.
    """
    where = tmp_path / "token"
    where.write_text("", encoding="utf-8")
    assert token_at(where).strip()
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_a_directory_where_the_file_goes_is_not_silently_accepted(tmp_path: Path) -> None:
    """It cannot be read and cannot be created, so it has to be an error."""
    (tmp_path / "token").mkdir()
    with pytest.raises(OSError, match="Is a directory"):
        token_at(tmp_path / "token")


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
