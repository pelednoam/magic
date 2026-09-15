"""What the token file does when it, or the disk under it, is wrong.

Split from `test_tokenfile`, which covers the ordinary life of the file --
made once, read back, kept to its owner. These are the ways it arrives
damaged: corrupt bytes, a mode with no write bit, a short write, a disk that
does not keep what it was given. Every one of them used to end with the server
running on a credential nobody could present.
"""

from __future__ import annotations

import os
import stat
from typing import TYPE_CHECKING

import pytest

from mtgcoach.api.access import usable
from mtgcoach.api.seating import SEATS, Seating, written
from mtgcoach.api.tokenfile import TokenPathError, seating_at

if TYPE_CHECKING:
    from pathlib import Path

#: A seating a test can write to a file and expect back unchanged.
KNOWN = Seating({"you": "hunter2", "them": "hunter3"})


@pytest.mark.parametrize(
    "content",
    ["����", "tok en", "tok\ten", "café-token", "\x00\x01\x02"],
)
def test_a_damaged_file_is_replaced_rather_than_becoming_the_token(
    tmp_path: Path, content: str
) -> None:
    """A half-written or byte-damaged file used to become the live credential.

    `_read` decodes with `errors="replace"`, so corrupt bytes come back as a
    string of U+FFFD -- which is not empty, so it was accepted, printed, and
    could not be sent in an `Authorization` header by any client. The server
    ran with a token nobody could present.
    """
    where = tmp_path / "token"
    where.write_bytes(content.encode("utf-8", errors="replace"))
    made = seating_at(where)
    assert content not in set(made.tokens.values())
    assert all(usable(made.token(seat)) for seat in SEATS)
    assert where.read_text(encoding="utf-8") == written(made)


def test_a_short_token_somebody_chose_is_left_alone(tmp_path: Path) -> None:
    """Not a strength check.

    A short token is a weak one, but an operator who put one there chose it,
    it is their LAN, and the server prints it at every start where they can
    see it. Silently replacing a deliberate choice is a worse surprise than
    the one this guards against.
    """
    where = tmp_path / "token"
    where.write_text(written(KNOWN), encoding="utf-8")
    assert seating_at(where) == KNOWN


def test_a_file_with_no_write_bit_is_tightened_rather_than_refused(tmp_path: Path) -> None:
    """A 0400 token from a restrictive umask or a careful backup.

    The lock needs `O_RDWR`, which such a file refuses outright -- so the
    server would not start, contradicting the promise that a mode it can put
    right gets put right.
    """
    where = tmp_path / "token"
    where.write_text(written(KNOWN), encoding="utf-8")
    where.chmod(0o400)
    assert seating_at(where) == KNOWN
    assert stat.S_IMODE(where.stat().st_mode) == 0o600


def test_a_token_is_written_whole_even_when_the_write_is_short(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`os.write` may write fewer bytes than it was given.

    A short write would hand the running server the whole token and leave a
    prefix on disk, so the next start -- and any other process -- would
    disagree with it about what the credential is.
    """
    real = os.write

    def grudging(handle: int, payload: bytes) -> int:
        """One byte at a time, which is allowed and rarely exercised."""
        return real(handle, payload[:1])

    monkeypatch.setattr(os, "write", grudging)
    where = tmp_path / "token"
    made = seating_at(where)
    assert where.read_text(encoding="utf-8") == written(made)


def test_a_file_that_cannot_be_opened_at_all_says_so(tmp_path: Path) -> None:
    """A directory that will not take a new file.

    Tightening the mode is the recovery for a file this user owns; there is
    none for a path this user cannot write to at all, and errno prose says
    nothing about what to do. The message names the path and asks who owns it.
    """
    where = tmp_path / "locked" / "token"
    where.parent.mkdir()
    where.parent.chmod(0o500)
    try:
        with pytest.raises(TokenPathError, match="cannot be opened for writing"):
            seating_at(where)
    finally:
        where.parent.chmod(0o700)


def test_a_write_the_disk_did_not_keep_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Truncate-then-write is not atomic.

    A crash or a full disk part-way leaves a prefix -- one seat with a usable
    token and one with a guessable one, which `seating.parsed` would refuse
    only after throwing the good half away with it. Reading it back makes that
    a refusal now, while somebody is watching.
    """
    real = os.write

    def losing(handle: int, payload: bytes) -> int:
        """Write half, and claim all of it."""
        real(handle, payload[: len(payload) // 2])
        return len(payload)

    monkeypatch.setattr(os, "write", losing)
    with pytest.raises(TokenPathError, match="did not keep what was written"):
        seating_at(tmp_path / "token")
