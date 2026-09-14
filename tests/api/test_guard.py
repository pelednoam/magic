"""The one check the reducer cannot make for itself.

``PlayLand``'s docstring in ``core`` says the rules engine cannot tell whether
the card is a land, because ``core`` holds no card data, and that the check
"arrives with the card database". These are that check.
"""

from __future__ import annotations

from dataclasses import replace

import pytest
from helpers_coach import Book

from helpers import ME, YOU, deck, facts
from mtgcoach.api.eventspec import BadEventError
from mtgcoach.api.guard import check
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import AdvanceStep, PlayLand
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.state import GameState, start_game

BOOK = Book(
    cards={
        "Forest": facts("Forest", land=True),
        "Bear": facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True),
    }
)


def _holding(oracle: str) -> tuple[CardInstance, ...]:
    return (CardInstance(InstanceId("card"), OracleId(oracle)),)


def _game(oracle: str) -> GameState:
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    mine = replace(state.player(ME), hand=_holding(oracle))
    return replace(state, players={**state.players, ME: mine})


def test_a_land_may_be_played_as_a_land() -> None:
    check(PlayLand(ME, InstanceId("card")), _game("Forest"), BOOK)


def test_a_creature_may_not() -> None:
    """CR 305.1. Otherwise the tracker keeps a Grizzly Bears as a land all game."""
    with pytest.raises(BadEventError, match="Grizzly Bears is not a land"):
        check(PlayLand(ME, InstanceId("card")), _game("Bear"), BOOK)


def test_an_unmodelled_card_is_allowed_through() -> None:
    """At 52% modelled, refusing what we cannot identify makes this unusable.

    The player can see their own card. Refusing what we *can* identify is the
    win; refusing what we cannot would be a different tool.
    """
    check(PlayLand(ME, InstanceId("card")), _game("Mystery"), BOOK)


def test_a_card_that_is_not_in_hand_is_left_to_the_reducer() -> None:
    """It says so too, and better -- with the zone it actually found it in."""
    check(PlayLand(ME, InstanceId("elsewhere")), _game("Forest"), BOOK)


def test_events_that_need_no_card_data_pass_straight_through() -> None:
    check(AdvanceStep(), _game("Forest"), BOOK)
