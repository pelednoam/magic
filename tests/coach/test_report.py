"""The answer a player actually asks for: what can I do this turn?

Each test is a board a beginner could actually be looking at, and the assertion
is the sentence the coach should be saying about it.
"""

from __future__ import annotations

from dataclasses import replace

from helpers import ME, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.report import advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
GROWTH = facts("Giant Growth", "{G}", instant=True)
OGRE = facts("Ogre", "{3}{R}", power=3, toughness=3, creature=True)

BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR, "Growth": GROWTH, "Ogre": OGRE},
    # A card is modelled when it has an entry here, even an empty one: a
    # vanilla creature is fully understood, it simply does nothing. A card
    # *missing* from this map is one the coach cannot speak for.
    rules={"Forest": FOREST_RULES, "Bear": (), "Growth": (), "Ogre": ()},
)


# --- the hand ---------------------------------------------------------------


def test_a_land_in_hand_can_be_played_on_your_main_phase() -> None:
    (card,) = advise(game(hand=("Forest",)), ME, BOOK).hand
    assert card.name == "Forest"
    assert card.playable


def test_a_second_land_cannot() -> None:
    state = game(hand=("Forest", "Forest"))
    state = replace(
        state, players={**state.players, ME: replace(state.player(ME), lands_played_this_turn=1)}
    )
    for card in advise(state, ME, BOOK).hand:
        assert "already played a land" in " ".join(card.reasons)


def test_a_creature_you_cannot_afford_says_how_short_you_are() -> None:
    (card,) = advise(game(hand=("Bear",), battlefield=("Forest",)), ME, BOOK).hand
    assert not card.playable
    assert "you need 1 more untapped source" in " ".join(card.reasons)


def test_a_creature_you_can_afford_comes_with_the_lands_to_tap() -> None:
    report = advise(game(hand=("Bear",), battlefield=("Forest", "Forest")), ME, BOOK)
    (card,) = report.hand
    assert card.playable
    assert card.payment is not None
    assert len(card.payment.tapped) == 2


def test_the_payment_keeps_the_most_useful_lands_untapped() -> None:
    """Three Forests and a two-mana spell: two get tapped, one stays up."""
    board = ("Forest", "Forest", "Forest")
    (card,) = advise(game(hand=("Bear",), battlefield=board), ME, BOOK).hand
    assert card.payment is not None
    assert len(card.payment.spare) == 1


def test_an_instant_is_castable_on_their_turn() -> None:
    state = game(hand=("Growth",), battlefield=("Forest",), step=Step.UPKEEP, active="you")
    (card,) = advise(state, ME, BOOK).hand
    assert card.playable


def test_a_creature_is_not_castable_on_their_turn() -> None:
    state = game(hand=("Bear",), battlefield=("Forest", "Forest"), step=Step.UPKEEP, active="you")
    (card,) = advise(state, ME, BOOK).hand
    assert "your own turn" in " ".join(card.reasons)


def test_playable_lists_only_what_you_can_actually_do() -> None:
    state = game(hand=("Forest", "Bear"), battlefield=())
    report = advise(state, ME, BOOK)
    assert [c.name for c in report.playable] == ["Forest"]


# --- cards the coach cannot speak for ---------------------------------------


def test_an_unmodelled_card_says_so_rather_than_saying_no() -> None:
    """Silence would read as "there is nothing to do", which is a lie."""
    report = advise(game(hand=("Mystery",)), ME, BOOK)
    (card,) = report.hand
    assert "not modelled" in " ".join(card.reasons)
    assert report.unknown == ("Mystery",)


def test_an_unmodelled_permanent_is_named_too() -> None:
    report = advise(game(battlefield=("Mystery",)), ME, BOOK)
    assert report.unknown == ("Mystery",)


def test_a_fully_modelled_board_reports_nothing_unknown() -> None:
    assert advise(game(hand=("Bear",), battlefield=("Forest",)), ME, BOOK).unknown == ()


# --- the frame --------------------------------------------------------------


def test_the_report_says_where_in_the_turn_you_are() -> None:
    report = advise(game(step=Step.UPKEEP), ME, BOOK)
    assert report.step is Step.UPKEEP
    assert report.turn == 1
    assert report.your_turn
    assert report.life == 20


def test_it_knows_when_it_is_not_your_turn() -> None:
    assert not advise(game(active="you"), ME, BOOK).your_turn


def test_a_reminder_falls_back_to_the_identifier_when_the_name_is_unknown() -> None:
    """The fixture knows the ability; the card database does not know the card.

    Reporting the trigger anyway is right -- the ability is modelled -- and
    naming it by its identifier is better than not mentioning it.
    """
    book = Book(
        cards=BOOK.cards,
        rules={
            **BOOK.rules,
            "Nameless": (TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ()),),
        },
    )
    state = game(battlefield=("Nameless",), step=Step.UPKEEP)
    (reminder,) = advise(state, ME, book).reminders
    assert reminder.name == "Nameless"
