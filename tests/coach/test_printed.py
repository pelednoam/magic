"""The cards in a position, and what they say.

A rules question about an ability used to reach the model with the ability
flagged and the instruction withheld -- "Dazzling Angel, 2/3, Flying, has rules
text not shown here" -- so the answer came from whatever a model remembered
about a card with that name. These are about the evidence that replaced it:
that the text arrives, once per card rather than once per permanent, from every
zone the asking player may read, and from none they may not.
"""

from __future__ import annotations

import pytest

from helpers import ME, YOU, facts
from helpers_coach import Book, game, instance, on_battlefield
from mtgcoach.coach.printed import PrintedCard, printed
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import PlayerId
from mtgcoach.core.player import PlayerState
from mtgcoach.core.stack import StackObject
from mtgcoach.core.state import GameState
from mtgcoach.core.steps import Step

ANGEL_TEXT = "Flying\nWhenever another creature you control enters, you gain 1 life."

BOOK = Book(
    cards={
        "Angel": facts("Dazzling Angel", "{2}{W}", "Flying", power=2, toughness=3, creature=True),
        "Forest": facts("Forest", land=True),
        "Growth": facts("Giant Growth", "{G}", instant=True),
        "Spawn": facts("Vampire Spawn", "{2}{B}", power=2, toughness=3, creature=True),
    },
    rules={"Angel": (), "Forest": (), "Growth": (), "Spawn": ()},
    texts={
        "Angel": ANGEL_TEXT,
        "Forest": "({T}: Add {G}.)",
        "Growth": "Target creature gets +3/+3 until end of turn.",
        "Spawn": "When this creature enters, each opponent loses 2 life and you gain 2 life.",
    },
)


def test_the_text_of_a_card_on_the_battlefield_arrives() -> None:
    """The sentence that answers the question, which used to be absent."""
    (card,) = printed(game(battlefield=("Angel",)), ME, BOOK)
    assert card == PrintedCard("Dazzling Angel", ANGEL_TEXT)


def test_a_card_is_quoted_once_however_many_copies_are_out() -> None:
    """Four Forests are one card. Printing the text four times buys nothing."""
    state = game(battlefield=("Forest", "Forest", "Forest"))
    assert [card.name for card in printed(state, ME, BOOK)] == ["Forest"]


def test_both_battlefields_and_your_own_hand_are_read() -> None:
    state = game(battlefield=("Angel",), hand=("Growth",), theirs=("Spawn",))
    assert [card.name for card in printed(state, ME, BOOK)] == [
        "Dazzling Angel",
        "Vampire Spawn",
        "Giant Growth",
    ]


def test_the_opponents_hand_is_not_read() -> None:
    """Hidden information (CR 400.2).

    A coach that quoted the other player's hand into an answer would be
    teaching a nine-year-old to cheat, and would do it in the one place the
    family has decided to trust.
    """
    theirs = PlayerState(
        library=(),
        hand=(instance("Growth"),),
        battlefield=(),
        graveyard=(),
        exile=(),
    )
    state = GameState(
        turn=1,
        active_player=ME,
        step=Step.PRECOMBAT_MAIN,
        players={ME: PlayerState((), (), (), (), ()), YOU: theirs},
    )
    assert printed(state, ME, BOOK) == ()


def test_a_spell_waiting_on_the_stack_is_read() -> None:
    """The card a question is most often about: the one nobody has resolved."""
    mine = PlayerState(
        library=(),
        hand=(),
        battlefield=(on_battlefield("Angel"),),
        graveyard=(),
        exile=(),
    )
    # The stack is one shared, ordered zone on the game (CR 405.1), not a
    # tuple on each player -- each object carries the player who cast it.
    state = GameState(
        turn=1,
        active_player=ME,
        step=Step.PRECOMBAT_MAIN,
        players={ME: mine, YOU: PlayerState((), (), (), (), ())},
        stack=(StackObject(instance("Growth"), ME),),
    )
    assert [card.name for card in printed(state, ME, BOOK)] == [
        "Dazzling Angel",
        "Giant Growth",
    ]


def test_a_card_the_book_has_never_heard_of_says_so_rather_than_nothing() -> None:
    """An empty line reads as "this card does nothing", which is a lie.

    Aegis Turtle really has no rules text; a card missing from the store has
    none *on file*, and those are different facts about the game.
    """
    (card,) = printed(game(battlefield=("Mystery",)), ME, BOOK)
    assert card.text == ""
    assert "no rules text on file" in card.described()
    assert card.unreadable


def test_a_card_the_engine_cannot_carry_out_is_flagged_beside_its_text() -> None:
    """Beside the ability, not in another section, which is where it is read."""
    book = Book(
        cards={"Growth": facts("Giant Growth", "{G}", instant=True)},
        texts={"Growth": "Target creature gets +3/+3 until end of turn."},
    )
    (card,) = printed(game(hand=("Growth",)), ME, book)
    assert card.unreadable
    assert "+3/+3" in card.described()
    assert "cannot carry this card out" in card.described()


def test_a_player_who_is_not_in_the_game_is_refused() -> None:
    with pytest.raises(IllegalEventError):
        printed(game(), PlayerId("nobody"), BOOK)
