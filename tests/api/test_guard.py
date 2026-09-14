"""The one check the reducer cannot make for itself.

``PlayLand``'s docstring in ``core`` says the rules engine cannot tell whether
the card is a land, because ``core`` holds no card data, and that the check
"arrives with the card database". These are that check.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from helpers import ME, YOU, deck, facts
from helpers_coach import Book
from mtgcoach.api.eventspec import BadEventError
from mtgcoach.api.guard import check
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import AdvanceStep, PlayLand
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step

BOOK = Book(
    cards={
        "Forest": facts("Forest", land=True),
        "Bear": facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True),
    }
)


def _holding(oracle: str) -> tuple[CardInstance, ...]:
    return (CardInstance(InstanceId("card"), OracleId(oracle)),)


def _game(oracle: str, step: Step = Step.PRECOMBAT_MAIN) -> GameState:
    """A game with one card in hand, in a step where a land could be played."""
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    mine = replace(state.player(ME), hand=_holding(oracle))
    return replace(state, players={**state.players, ME: mine}, step=step)


def test_a_land_may_be_played_as_a_land() -> None:
    check(PlayLand(ME, InstanceId("card")), _game("Forest"), BOOK)


def test_a_creature_may_not() -> None:
    """CR 305.1. Otherwise the tracker keeps a Grizzly Bears as a land all game."""
    with pytest.raises(BadEventError, match="is not a land"):
        check(PlayLand(ME, InstanceId("card")), _game("Bear"), BOOK)


def test_a_land_may_not_be_played_outside_a_main_phase() -> None:
    """The server must not accept what the coach in the same breath refuses.

    It did: `play_land` during the untap step returned 200 while the advice in
    the very same response read "you can only play lands in a main phase".
    """
    with pytest.raises(BadEventError, match="only play lands in a main phase"):
        check(PlayLand(ME, InstanceId("card")), _game("Forest", Step.UNTAP), BOOK)


def test_a_land_may_not_be_played_on_the_opponents_turn() -> None:
    state = replace(_game("Forest"), active_player=YOU)
    with pytest.raises(BadEventError, match="your own turn"):
        check(PlayLand(ME, InstanceId("card")), state, BOOK)


def test_a_second_land_is_refused_by_the_server_too() -> None:
    """The reducer catches this as well; the point is that they agree."""
    state = _game("Forest")
    spent = replace(state.player(ME), hand=state.player(ME).hand, lands_played_this_turn=1)
    with pytest.raises(BadEventError, match="already played a land"):
        check(
            PlayLand(ME, InstanceId("card")),
            replace(state, players={**state.players, ME: spent}),
            BOOK,
        )


def test_a_card_the_coach_cannot_identify_is_refused() -> None:
    """Unknown is not permitted.

    No facts means the store has never seen the card, not that its rules are
    unmodelled -- different questions, different answers, and only the second
    is common. Nothing about an unknown card says "land", so allowing it
    reopened the hole this function exists to close.
    """
    with pytest.raises(BadEventError, match="does not know this card"):
        check(PlayLand(ME, InstanceId("card")), _game("Mystery"), BOOK)


def test_a_card_whose_rules_are_unmodelled_still_plays() -> None:
    """59 of the box's cards are this: identified, priced, not understood."""
    book = Book(cards={**BOOK.cards, "Odd": facts("Odd Land", land=True)})
    check(PlayLand(ME, InstanceId("card")), _game("Odd"), book)


def test_a_card_that_is_not_in_hand_is_left_to_the_reducer() -> None:
    """It says so too, and better -- with the zone it actually found it in."""
    check(PlayLand(ME, InstanceId("elsewhere")), _game("Forest"), BOOK)


def test_events_that_need_no_card_data_pass_straight_through() -> None:
    check(AdvanceStep(), _game("Forest"), BOOK)
