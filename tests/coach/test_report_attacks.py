"""Which attacks the coach puts in front of you, and when it will not.

The third case is the one that matters: a board the engine refuses to evaluate
comes back as a sentence, because an empty attack list reads as advice.
"""

from __future__ import annotations

from helpers import ME, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.report import advise
from mtgcoach.core.steps import Step

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
GROWTH = facts("Giant Growth", "{G}", instant=True)
OGRE = facts("Ogre", "{3}{R}", power=3, toughness=3, creature=True)

BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR, "Growth": GROWTH, "Ogre": OGRE},
    rules={"Forest": FOREST_RULES, "Bear": (), "Growth": (), "Ogre": ()},
)


def test_no_attacks_outside_your_combat() -> None:
    report = advise(game(battlefield=("Bear",)), ME, BOOK)
    assert report.attacks.plans == ()
    assert "declare attackers step" in report.attacks.unavailable


def test_no_attacks_on_their_turn() -> None:
    state = game(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS, active="you")
    assert "your own turn" in advise(state, ME, BOOK).attacks.unavailable


def test_the_attack_advisor_ranks_the_options() -> None:
    state = game(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS)
    report = advise(state, ME, BOOK)
    assert report.attacks.unavailable == ""
    assert report.attacks.plans[0].names == ("Grizzly Bears",)


def test_attacking_into_a_bigger_creature_is_not_the_best_plan() -> None:
    state = game(battlefield=("Bear",), theirs=("Ogre",), step=Step.DECLARE_ATTACKERS)
    assert advise(state, ME, BOOK).attacks.plans[0].names == ()


def test_lethal_is_found() -> None:
    state = game(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS, life=2)
    assert advise(state, ME, BOOK).attacks.plans[0].is_lethal


def test_a_noncreature_permanent_is_not_an_attacker() -> None:
    """A Forest on the battlefield is not a candidate to swing with."""
    state = game(battlefield=("Forest", "Bear"), step=Step.DECLARE_ATTACKERS)
    report = advise(state, ME, BOOK)
    assert all("Forest" not in plan.names for plan in report.attacks.plans)


def test_a_refusal_from_the_engine_reaches_the_player() -> None:
    """A blank attack section would read as "do not attack"."""
    star = facts("Consuming Aberration", "{3}{U}{B}", creature=True)
    book = Book(cards={**BOOK.cards, "Star": star}, rules=BOOK.rules)
    state = game(battlefield=("Star",), step=Step.DECLARE_ATTACKERS)
    assert "no fixed power" in advise(state, ME, book).attacks.unavailable
