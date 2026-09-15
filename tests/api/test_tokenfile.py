"""The token file: made once, kept to its owner, never followed through a link.

The disk half of the seating. `test_access_tokens` covers the wire half -- the
header a request carries -- and `test_seating` the middle half, which is which
seat a token names. The three have nothing in common, which is why the modules
were split in the first place.
"""

from __future__ import annotations

import stat
from typing import TYPE_CHECKING

import pytest

from mtgcoach.api.access import new_token
from mtgcoach.api.seating import SEATS, Seating, written
from mtgcoach.api.tokenfile import TokenPathError, seating_at

if TYPE_CHECKING:
    from pathlib import Path

#: A seating a test can write to a file and expect back unchanged.
KNOWN = Seating({"you": "already-yours", "them": "already-theirs"})


def test_a_fresh_token_is_not_guessable() -> None:
    assert len(new_token()) >= 32
    assert new_token() != new_token()


def test_a_token_file_is_made_once_and_read_back(tmp_path: Path) -> None:
    """Restarting the server must not invalidate the phone in somebody's hand."""
    where = tmp_path / "token"
    first = seating_at(where)
    assert seating_at(where) == first


def test_every_seat_gets_a_different_token(tmp_path: Path) -> None:
    """Two seats holding one token is the arrangement this replaces."""
    made = seating_at(tmp_path / "token")
    assert len({made.token(seat) for seat in SEATS}) == len(SEATS)


def test_a_token_file_is_readable_only_by_its_owner(tmp_path: Path) -> None:
    """Created with the permissions it needs, not fixed afterwards.

    A token that was briefly world-readable was world-readable.
    """
    where = tmp_path / "token"
    seating_at(where)
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_a_directory_that_does_not_exist_yet_is_made(tmp_path: Path) -> None:
    assert seating_at(tmp_path / "nested" / "token")


def test_an_empty_token_file_is_replaced(tmp_path: Path) -> None:
    """A truncated write should not leave the server with no access control."""
    where = tmp_path / "token"
    where.write_text("   \n", encoding="utf-8")
    assert seating_at(where)


def test_an_existing_loose_file_is_tightened(tmp_path: Path) -> None:
    """It can arrive from a git checkout, a backup, or a loose umask.

    The `open` mode is ignored by the kernel for a file that already exists, so
    the first version wrote a fresh token into somebody else's 0644 file and
    left it 0644.
    """
    where = tmp_path / "token"
    where.write_text(written(KNOWN), encoding="utf-8")
    where.chmod(0o644)
    assert seating_at(where) == KNOWN
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_the_single_token_this_file_used_to_hold_is_replaced(tmp_path: Path) -> None:
    """One token in this file was a credential for *both* seats.

    Reading it as either seat's token would keep the hole that a token per seat
    exists to close, so it is rotated instead -- both devices are told the new
    tokens and the old one stops working.
    """
    where = tmp_path / "token"
    where.write_text("old-single-token\n", encoding="utf-8")
    made = seating_at(where)
    assert "old-single-token" not in set(made.tokens.values())


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
        seating_at(link)
    assert elsewhere.read_text(encoding="utf-8") == "planted\n", "the target is untouched"


def test_a_second_server_reads_what_the_first_wrote(tmp_path: Path) -> None:
    """`O_EXCL` settles the race: one creates, the other reads.

    Without it both wrote different tokens over each other and a running app
    was guarded by one while the operator was shown the other.
    """
    where = tmp_path / "token"
    first = seating_at(where)
    assert seating_at(where) == first


def test_an_empty_file_is_written_over_rather_than_looped_on(tmp_path: Path) -> None:
    """The exclusive create says the file is there; the read says it is empty.

    The first version retried until one of those changed, which was never.
    """
    where = tmp_path / "token"
    where.write_text("", encoding="utf-8")
    assert seating_at(where)
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_a_directory_where_the_file_goes_is_not_silently_accepted(tmp_path: Path) -> None:
    """It cannot be read and cannot be created, so it has to be an error."""
    (tmp_path / "token").mkdir()
    with pytest.raises(OSError, match="Is a directory"):
        seating_at(tmp_path / "token")
