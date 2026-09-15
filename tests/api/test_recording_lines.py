"""Reading a journal line back, including the lines a killed run leaves.

Split from ``test_recording`` at the line limit, and the seam is the real one:
that file is about a game surviving the round trip, this one is about every way
a line can arrive damaged. A journal is written by a process that can be killed
at three in the morning, so a truncated tail is the normal shape of a bad line,
not an exotic one.
"""

from __future__ import annotations

import pytest

from helpers_replay import SEED
from mtgcoach.api.reading import recorded
from mtgcoach.api.recording import KIND
from mtgcoach.core.events import AdvanceStep, PlayLand
from mtgcoach.core.ids import InstanceId, PlayerId


@pytest.mark.parametrize(
    "line",
    [
        "not an object",
        {"kind": "decision"},
        {"kind": KIND, "seed": "seven", "first": "you", "decks": [], "libraries": {}},
        {"kind": KIND, "seed": SEED, "first": 1, "decks": [], "libraries": {}},
        {"kind": KIND, "seed": SEED, "first": "you", "decks": "green", "libraries": {}},
        {"kind": KIND, "seed": SEED, "first": "you", "decks": [], "libraries": "none"},
    ],
)
def test_a_line_that_is_not_a_recording_is_not_one(line: object) -> None:
    """Every way a line can fail to be a game, said once each.

    None rather than an exception: a journal holds decision lines too, and
    walking past one is the normal case, not an error.
    """
    assert recorded(line) is None


def test_a_recording_with_no_decks_still_reads() -> None:
    """A line whose deck names were lost still rebuilds the game.

    The names are a label on the screen; the libraries are the game. Refusing
    the whole recording over a missing label would lose the part that matters.
    """
    found = recorded({"kind": KIND, "seed": SEED, "first": "you", "decks": [], "libraries": {}})
    assert found is not None
    assert found.decks == ("", "")


@pytest.mark.parametrize(
    "libraries",
    [
        {"you": [["a", "Forest"], ["b"]]},
        {"you": [["a", "Forest"], "c"]},
        {"you": "not a library"},
    ],
)
def test_a_library_that_is_not_cards_is_refused(libraries: dict[str, object]) -> None:
    """Refused, not repaired.

    Dropping a malformed entry and carrying on shifts every card after it, so
    the game that rebuilds has different hands and different draws from the one
    that was played -- and nothing on screen says so. A game the screen refuses
    to show is much the better failure, and ``games_in`` skips just that game.
    """
    with pytest.raises(ValueError, match="you"):
        recorded(
            {
                "kind": KIND,
                "seed": SEED,
                "first": "you",
                "decks": ["green", "other"],
                "libraries": libraries,
            }
        )


def test_a_truncated_event_log_stops_where_it_was_cut() -> None:
    """And keeps what came before it.

    Skipping the bad entry and carrying on would rebuild a board that never
    existed -- the same events minus one is a *different* game, not a shorter
    one -- so the log ends where the file did.
    """
    lines: list[object] = [
        {"type": "advance_step"},
        {"type": "play_land", "player": "you", "instance_id": "you-0"},
        {"type": "no_such_event"},
        {"type": "advance_step"},
    ]
    found = recorded(
        {
            "kind": KIND,
            "seed": SEED,
            "first": "you",
            "decks": ["green", "other"],
            "libraries": {},
            "events": lines,
        }
    )
    assert found is not None
    assert found.events == (AdvanceStep(), PlayLand(PlayerId("you"), InstanceId("you-0")))


def test_an_entry_that_is_not_an_object_ends_the_log_too() -> None:
    """The other way a truncated line arrives."""
    found = recorded(
        {
            "kind": KIND,
            "seed": SEED,
            "first": "you",
            "decks": [],
            "libraries": {},
            "events": [{"type": "advance_step"}, "advance_step"],
        }
    )
    assert found is not None
    assert found.events == (AdvanceStep(),)


def test_events_that_are_not_a_list_are_no_events() -> None:
    """A line whose event log was lost is a game that did nothing."""
    found = recorded(
        {
            "kind": KIND,
            "seed": SEED,
            "first": "you",
            "decks": [],
            "libraries": {},
            "events": "lots",
        }
    )
    assert found is not None
    assert found.events == ()


@pytest.mark.parametrize(
    "cards",
    [
        [[None, "Forest"]],
        [["a", 3]],
        [["", "Forest"]],
        [["a", ""]],
    ],
)
def test_a_card_whose_ids_are_not_strings_is_refused(cards: list[object]) -> None:
    """Not coerced. ``[null, 3]`` used to become the card ``("None", "3")``.

    Which looks perfectly usable, gets dealt into a game, and is a card that
    was never in the deck -- so every board after it is a board that never
    existed.
    """
    with pytest.raises(ValueError, match="non-empty strings"):
        recorded(
            {
                "kind": KIND,
                "seed": SEED,
                "first": "you",
                "decks": [],
                "libraries": {"you": cards},
            }
        )


def test_two_cards_may_not_share_an_instance_id() -> None:
    """`InstanceId` exists so the Mountain you tapped is not the other one.

    Every zone movement is looked up by it, so a duplicate makes one of the two
    unreachable and the other ambiguous.
    """
    with pytest.raises(ValueError, match="share an instance id"):
        recorded(
            {
                "kind": KIND,
                "seed": SEED,
                "first": "you",
                "decks": [],
                "libraries": {"you": [["a", "Forest"], ["a", "Island"]]},
            }
        )
