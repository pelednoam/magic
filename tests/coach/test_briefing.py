"""What the model is told.

Every fact in the prompt has already been checked by the engine, so these
assert that the checked facts actually arrive -- and that the things the engine
could *not* check arrive labelled as such.
"""

from __future__ import annotations

from helpers import ME, UNKNOWN_ABILITY, facts
from helpers_coach import Book, game, land, taps_for
from mtgcoach.coach.briefing import brief
from mtgcoach.coach.report import advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent


def _flat(text: str) -> str:
    """The prompt with its line wrapping removed.

    The rules are wrapped for a reader; asserting on a phrase that happens to
    span a line break tests the wrapping, not the instruction.
    """
    return " ".join(text.split())


FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
OGRE = facts("Ogre", "{3}{R}", power=3, toughness=3, creature=True)
BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR, "Ogre": OGRE},
    rules={"Forest": FOREST_RULES, "Bear": (), "Ogre": ()},
)


def test_the_rules_come_first_and_say_what_is_discarded() -> None:
    """A model that knows its prose is binned has a reason to use the schema."""
    text = _flat(brief(advise(game(), ME, BOOK)))
    assert "discarded unread" in text
    assert "nine-year-old" in text


def test_a_playable_card_arrives_with_its_identity() -> None:
    """The model answers with an id, so it has to be given one."""
    report = advise(game(hand=("Forest",)), ME, BOOK)
    (card,) = report.hand
    text = brief(report)
    assert f"PLAYABLE  {card.instance_id}  Forest" in text


def test_an_unplayable_card_arrives_with_the_engine_s_reason() -> None:
    text = brief(advise(game(hand=("Bear",), battlefield=("Forest",)), ME, BOOK))
    assert "no        Grizzly Bears: you need 1 more untapped source" in text


def test_the_payment_is_summarised_not_spelled_out() -> None:
    """Which lands is the app's job; how many is what the advice turns on."""
    board = ("Forest", "Forest", "Forest")
    text = brief(advise(game(hand=("Bear",), battlefield=board), ME, BOOK))
    assert "tap 2, keeps 1 up" in text


def test_an_empty_hand_says_so() -> None:
    assert "HAND: empty." in brief(advise(game(), ME, BOOK))


def test_attacks_arrive_with_the_maths_the_engine_did() -> None:
    state = game(battlefield=("Bear",), theirs=("Ogre",), step=Step.DECLARE_ATTACKERS)
    text = brief(advise(state, ME, BOOK))
    assert "ATTACKS (best first" in text
    assert "Grizzly Bears [" in text
    assert "damage" in text


def test_a_lethal_attack_is_unmissable() -> None:
    state = game(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS, life=2)
    assert "THIS WINS THE GAME" in brief(advise(state, ME, BOOK))


def test_a_blocker_the_attack_would_kill_is_named() -> None:
    """The trade is the advice, so both halves of it have to be in the prompt.

    At three life the defender cannot take three damage, so the block is
    forced -- and a 2/2 in front of a 3/3 dies for it.
    """
    state = game(battlefield=("Ogre",), theirs=("Bear",), step=Step.DECLARE_ATTACKERS, life=3)
    assert "kills Grizzly Bears" in brief(advise(state, ME, BOOK))


def test_holding_back_is_offered_as_an_option() -> None:
    state = game(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS)
    assert "nobody" in brief(advise(state, ME, BOOK))


def test_no_combat_says_why_rather_than_showing_nothing() -> None:
    text = brief(advise(game(battlefield=("Bear",)), ME, BOOK))
    assert "ATTACKS: none to consider" in text
    assert "declare attackers step" in text


def test_triggers_are_named() -> None:
    rings = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())
    book = Book(
        cards={**BOOK.cards, "Bell": facts("Bell", creature=True, power=1, toughness=1)},
        rules={**BOOK.rules, "Bell": (rings,)},
    )
    state = game(battlefield=("Bell",), step=Step.UPKEEP)
    assert "TRIGGERS NOW: Bell" in brief(advise(state, ME, book))


def test_a_turn_with_no_triggers_says_nothing_about_them() -> None:
    assert "TRIGGERS NOW" not in brief(advise(game(), ME, BOOK))


def test_a_fully_modelled_board_says_so_explicitly() -> None:
    """So the model knows the silence is an answer, not an omission."""
    assert "CANNOT SPEAK FOR: nothing" in brief(advise(game(hand=("Forest",)), ME, BOOK))


def test_what_the_engine_cannot_speak_for_is_listed_and_demanded() -> None:
    book = Book(
        cards={**BOOK.cards, "Puzzle": facts("Puzzle", "{2}{U}")},
        rules={**BOOK.rules, "Puzzle": (UNKNOWN_ABILITY,)},
    )
    text = brief(advise(game(hand=("Puzzle",)), ME, book))
    assert "CANNOT SPEAK FOR" in text
    assert "  - Puzzle" in text
    assert "must appear in check_yourself" in _flat(text)


def test_where_in_the_turn_it_is() -> None:
    text = brief(advise(game(step=Step.UPKEEP), ME, BOOK))
    assert "turn 1, upkeep, your turn" in text
    assert "20 life" in text


def test_it_knows_when_it_is_not_your_turn() -> None:
    assert "their turn" in brief(advise(game(active="you2"), ME, BOOK))


def test_a_mana_ability_does_not_leak_into_the_hand_listing() -> None:
    """The briefing is about choices, not about everything that is true."""
    book = Book(cards={"Forest": FOREST}, rules={"Forest": (taps_for("{G}"),)})
    assert "{T}" not in brief(advise(game(battlefield=("Forest",)), ME, book))
