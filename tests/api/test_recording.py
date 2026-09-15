"""Writing a whole game down, and reading it back.

The format a step-through rests on: if these fail, the board a child is shown
stepping through a game is not the board that was played.

``test_recording_lines`` is the other half -- every way a journal line can
arrive damaged.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

import pytest

from helpers_replay import DECK, SEED, opening, played, recording
from mtgcoach.api.reading import recorded
from mtgcoach.api.recording import Recording, dealt_as
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import MoveCard, PlayLand
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.reduce import replay
from mtgcoach.core.state import start_game
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState

#: How many cards an opening hand is, so a deal can be checked against it.
OPENING_HAND = 7


def rebuilt(line: str) -> Recording:
    """A recording written down and read back, as a journal does it."""
    found = recorded(cast("dict[str, object]", json.loads(line)))
    assert found is not None
    return found


def test_a_game_survives_being_written_down_and_read_back() -> None:
    """The whole contract, in one assertion.

    If this fails, the board a child is shown stepping through a game is not
    the board that was played -- which is the one thing this format exists to
    prevent.
    """
    original = recording()
    assert rebuilt(original.as_json()) == original


def test_the_rebuilt_game_reaches_the_same_board() -> None:
    """And the events, folded, land where the real game landed."""
    original = recording()
    there = replay(original.opening(), original.events)
    back = rebuilt(original.as_json())
    assert replay(back.opening(), back.events) == there


def test_the_deal_is_written_hand_first() -> None:
    """Because ``start_game`` takes the opening hand off the front.

    Library first rebuilds a differently-ordered deck and therefore a different
    game -- which it silently did, once, and every rebuilt board was wrong.
    """
    dealt = dealt_as(opening())
    assert [name for _, name in dealt["you"][:OPENING_HAND]] == list(DECK[:OPENING_HAND])


def test_the_deal_rebuilds_the_hand_it_was_taken_from() -> None:
    """The same thing said as a round trip, which is how it is used."""
    before = opening()
    dealt = dealt_as(before)
    after = start_game(
        {
            PlayerId(seat): tuple(
                CardInstance(InstanceId(instance), OracleId(oracle)) for instance, oracle in cards
            )
            for seat, cards in dealt.items()
        },
        first_player=PlayerId("you"),
    )
    assert after == before


@pytest.mark.parametrize("zone", [ZoneName.BATTLEFIELD, ZoneName.GRAVEYARD, ZoneName.EXILE])
def test_a_game_already_under_way_is_not_a_deal(zone: ZoneName) -> None:
    """Refused rather than written down wrong.

    A card anywhere but the hand or the library means this is not the opening,
    and no ordering of it would rebuild the game.
    """
    state = _moved(opening(), zone)
    with pytest.raises(ValueError, match="not a game's opening state"):
        dealt_as(state)


def _moved(state: GameState, zone: ZoneName) -> GameState:
    """The opening board with one card out of hand."""
    card = state.players[PlayerId("you")].hand[0]
    return replay(state, (MoveCard(PlayerId("you"), card.instance_id, zone),))


def test_the_opening_refuses_libraries_that_are_not_a_game() -> None:
    """Two players, or it is not a game to rebuild."""
    with pytest.raises(ValueError, match="exactly 2 players"):
        Recording(seed=SEED, decks=("a", "b"), first="you").opening()


def test_the_events_of_the_fixture_game_are_the_ones_it_played() -> None:
    """Guard on the fixture: an empty log would make half of this vacuous."""
    assert PlayLand(PlayerId("you"), InstanceId("you-0")) in played()
