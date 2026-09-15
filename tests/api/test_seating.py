"""One token per seat: what counts as a seating, and which seat a token names.

The middle half of the three. `test_access` is the door -- whether a request
gets in at all -- `test_tokenfile` is the file the tokens live in, and this is
the part that decides *who*.

It is small and it is the whole of the identity, so every way it can refuse has
a test: a seat without a token, a token no header could carry, and -- the one
that matters most -- two seats holding the same token, which is one token and
is the arrangement this module exists to replace.
"""

from __future__ import annotations

import pytest

from mtgcoach.api.access import MissingTokenError
from mtgcoach.api.seating import SEATS, Seating, fresh, parsed, written

MINE, THEIRS = SEATS

#: A seating written out by hand, so a test can say what it expects back.
KNOWN = Seating({MINE: "mine", THEIRS: "theirs"})


# --- what counts as a seating -------------------------------------------------


def test_a_seat_without_a_token_is_refused() -> None:
    with pytest.raises(MissingTokenError, match="needs a token for each"):
        Seating({MINE: "mine"})


def test_a_seat_nobody_sits_in_is_refused() -> None:
    """A credential for a seat the game does not deal is a credential for nothing."""
    with pytest.raises(MissingTokenError, match="needs a token for each"):
        Seating({MINE: "mine", THEIRS: "theirs", "umpire": "theirs-too"})


@pytest.mark.parametrize("token", ["", "   ", "tok en", "café", "tok\ten"])
def test_a_token_no_header_could_carry_is_refused(token: str) -> None:
    """The same rule `access.usable` applies, applied on construction.

    A server that started with one of these would print a token no client could
    present, and every request from that device would be a 401 that reads as
    "wrong token" to somebody holding the right one.
    """
    with pytest.raises(MissingTokenError, match="Authorization header"):
        Seating({MINE: "mine", THEIRS: token})


def test_two_seats_sharing_a_token_are_refused() -> None:
    """One token for both seats is one token.

    Which is exactly what this replaced: with one secret, the `player` field in
    an event was a claim the sender made about itself and nothing could check
    it. A seating that allowed it would put that back silently.
    """
    with pytest.raises(MissingTokenError, match="two seats share a token"):
        Seating({MINE: "same", THEIRS: "same"})


# --- which seat a token names -------------------------------------------------


def test_each_token_names_its_own_seat() -> None:
    assert KNOWN.seat("mine") == MINE
    assert KNOWN.seat("theirs") == THEIRS


def test_a_token_that_is_not_either_names_nobody() -> None:
    assert KNOWN.seat("neither") is None


def test_no_token_at_all_names_nobody() -> None:
    """Rather than matching whichever seat has a falsy token, which cannot exist."""
    assert KNOWN.seat("") is None


def test_a_seat_hands_back_its_own_token_for_printing() -> None:
    """The server prints them at startup; there is nobody to email them to."""
    assert KNOWN.token(THEIRS) == "theirs"


def test_asking_for_a_seat_that_does_not_exist_is_a_mistake_not_a_default() -> None:
    with pytest.raises(KeyError):
        KNOWN.token("umpire")


# --- making one, and reading one back -----------------------------------------


def test_a_fresh_seating_gives_every_seat_a_different_token() -> None:
    """Derived tokens would mean holding one seat's is holding the other's."""
    made = fresh()
    assert {*made.tokens} == {*SEATS}
    assert len({*made.tokens.values()}) == len(SEATS)


def test_what_is_written_reads_back_as_what_was_written() -> None:
    assert parsed(written(KNOWN)) == KNOWN


def test_the_file_is_written_in_seat_order() -> None:
    """So the file and the printout are two lists in the same order."""
    assert written(KNOWN).splitlines() == [f"{MINE} mine", f"{THEIRS} theirs"]


def test_no_proper_prefix_of_a_written_seating_is_read_as_one() -> None:
    """A file caught half-written is not a seating, at any length.

    Truncation used to be invisible, and it was the worst way for this to fail:
    cut ``them <token>`` short anywhere and what is left is still a well-formed
    line holding a shorter token, which the server would then accept as that
    seat's credential -- a one-character one, if the write stopped that early.
    A crash mid-write and a full disk both produce exactly that file.

    Every prefix, rather than a couple of hand-picked ones, because the bug was
    that *some* lengths parse and there is no interesting length to pick.
    """
    whole = written(fresh())
    for cut in range(len(whole)):
        assert parsed(whole[:cut]) is None, f"{whole[:cut]!r} is not a whole seating"


def test_a_seating_that_reads_back_is_one_the_writer_finished() -> None:
    """The guard on the guard: the whole file is still read, not just refused."""
    assert parsed(written(KNOWN)) == KNOWN


@pytest.mark.parametrize(
    ("text", "why"),
    [
        ("", "an empty file"),
        ("you mine\nthem theirs", "a file with no newline after its last line"),
        ("you mine\nthem th", "a second line cut short mid-token"),
        ("   \n\n", "a file of whitespace"),
        ("one-single-token\n", "the single token this file used to hold"),
        ("you mine them theirs\n", "one line with everything on it"),
        ("you mine\n", "a seat missing"),
        ("you mine\nyou theirs\n", "the same seat twice"),
        ("you mine\nthem mine\n", "one token for both seats"),
        ("you mine\nthem \n", "a seat whose token is missing"),
    ],
)
def test_what_is_not_a_seating_is_not_read_as_one(text: str, why: str) -> None:
    """None rather than a raise, and strictly.

    The caller's answer to "this is not a seating" is to make a fresh one, and
    that is the right answer to every way it can fail to be one. The single
    token is the case to be strict about: it was a credential for *both* seats,
    so reading it as either would keep the hole a token per seat closes.
    """
    assert parsed(text) is None, why
