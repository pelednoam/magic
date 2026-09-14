"""Checking the coach against the engine.

§8 says Claude is never the source of truth for rules. That is a promise you
cannot keep by asking nicely, because a fluent wrong answer reads exactly like
a fluent right one. These are the checks that keep it.
"""

from __future__ import annotations

import pytest

from helpers import ME, UNKNOWN_ABILITY, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.advice import (
    SHOWN_ATTACKS,
    Explanation,
    offered,
    refusal,
    trusted,
    verify,
)
from mtgcoach.coach.report import TurnReport, advise
from mtgcoach.core.steps import Step

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR},
    rules={"Forest": FOREST_RULES, "Bear": ()},
)


def _main(hand: tuple[str, ...] = (), battlefield: tuple[str, ...] = ()) -> TurnReport:
    """A board in a main phase."""
    return advise(game(hand=hand, battlefield=battlefield), ME, BOOK)


def _combat(battlefield: tuple[str, ...] = ()) -> TurnReport:
    """A board at the moment attackers are declared."""
    return advise(game(battlefield=battlefield, step=Step.DECLARE_ATTACKERS), ME, BOOK)


# --- what it may recommend playing -------------------------------------------


def test_recommending_a_playable_card_is_fine() -> None:
    report = _main(hand=("Forest",))
    (card,) = report.hand
    assert trusted(Explanation(play=str(card.instance_id)), report)


def test_recommending_a_card_that_is_not_in_hand_is_refused() -> None:
    """The commonest way a model is wrong: it invents the option."""
    report = _main(hand=("Forest",))
    (problem,) = verify(Explanation(play="nothing-like-this"), report)
    assert "not in hand" in problem


def test_recommending_a_card_the_engine_refused_is_refused() -> None:
    """And the reason comes along, so the failure is diagnosable."""
    report = _main(hand=("Bear",), battlefield=("Forest",))
    (card,) = report.hand
    (problem,) = verify(Explanation(play=str(card.instance_id)), report)
    assert "cannot be played" in problem
    assert "untapped source" in problem


def test_recommending_nothing_is_a_real_recommendation() -> None:
    assert trusted(Explanation(play=""), _main(hand=("Forest",)))


# --- what it may recommend attacking with ------------------------------------


def test_an_attack_the_engine_evaluated_is_fine() -> None:
    report = _combat(battlefield=("Bear",))
    best = next(p for p in report.attacks.plans if p.attackers)
    ids = tuple(str(c.instance_id) for c in best.attackers)
    assert trusted(Explanation(attack=ids), report)


def test_the_creatures_are_matched_as_a_set_not_a_sequence() -> None:
    """Order is not a decision, so it is not a difference."""
    report = _combat(battlefield=("Bear", "Bear"))
    both = next(p for p in report.attacks.plans if len(p.attackers) == 2)
    ids = tuple(reversed([str(c.instance_id) for c in both.attackers]))
    assert trusted(Explanation(attack=ids), report)


def test_an_attack_the_engine_never_evaluated_is_refused() -> None:
    """Not a bolder choice -- one nobody worked out the consequences of."""
    report = _combat(battlefield=("Bear",))
    (problem,) = verify(Explanation(attack=("a-creature-from-nowhere",)), report)
    assert "did not evaluate" in problem


def test_a_subset_of_a_plan_is_still_a_different_attack() -> None:
    report = _combat(battlefield=("Bear", "Bear"))
    both = next(p for p in report.attacks.plans if len(p.attackers) == 2)
    one = (str(both.attackers[0].instance_id), "extra")
    assert verify(Explanation(attack=one), report)


def test_attacking_when_there_is_no_combat_is_refused() -> None:
    report = _main(battlefield=("Bear",))
    (problem,) = verify(Explanation(attack=("anything",)), report)
    assert "the engine gave no plans" in problem
    assert "declare attackers step" in problem


def test_not_attacking_needs_no_plan() -> None:
    assert trusted(Explanation(attack=()), _main(battlefield=("Bear",)))


# --- where the engine stops, the coach has to say so -------------------------


def test_silence_about_an_unmodelled_card_is_refused() -> None:
    """Silence reads as "counted and unimportant".

    A model that forgets is indistinguishable from one that decided the card
    did not matter. §8 requires the caveat; this is what requires it.
    """
    book = Book(
        cards={**BOOK.cards, "Puzzle": facts("Puzzle", "{2}{U}")},
        rules={**BOOK.rules, "Puzzle": (UNKNOWN_ABILITY,)},
    )
    report = advise(game(hand=("Puzzle",)), ME, book)
    (problem,) = verify(Explanation(), report)
    assert "not modelled" in problem
    assert "Puzzle" in problem


def test_naming_it_is_enough() -> None:
    book = Book(
        cards={**BOOK.cards, "Puzzle": facts("Puzzle", "{2}{U}")},
        rules={**BOOK.rules, "Puzzle": (UNKNOWN_ABILITY,)},
    )
    report = advise(game(hand=("Puzzle",)), ME, book)
    assert trusted(Explanation(check_yourself=("Puzzle does something I can't read",)), report)


def test_a_fully_modelled_board_owes_no_caveat() -> None:
    assert trusted(Explanation(), _main(hand=("Forest",)))


# --- more than one thing can be wrong at once --------------------------------


def test_every_problem_is_reported_not_just_the_first() -> None:
    report = _main(hand=("Bear",), battlefield=("Forest",))
    (card,) = report.hand
    problems = verify(Explanation(play=str(card.instance_id), attack=("nowhere",)), report)
    assert len(problems) == 2


# --- what the player sees when it fails --------------------------------------


def test_a_refusal_says_why_and_points_at_what_is_still_right() -> None:
    """Not silence, and not the broken advice."""
    shown = refusal(("recommends an attack the engine did not evaluate",))
    assert "disagreed with the rules engine" in shown.because
    assert "checked" in shown.in_short
    assert shown.watch_out
    assert shown.play == ""
    assert shown.attack == ()


def test_an_attack_past_the_ones_shown_is_refused() -> None:
    """Recommend only from the options below means the options below.

    The prompt lists the first few plans. Accepting one past the cut credits a
    model with choosing something it was never shown -- and that plan is one
    nobody read the consequences of, which is the whole value of the list.
    """
    report = _combat(battlefield=("Bear",) * 5)
    if len(report.attacks.plans) <= SHOWN_ATTACKS:
        pytest.fail("the fixture must produce more plans than the prompt shows")
    beyond = report.attacks.plans[SHOWN_ATTACKS]
    said = Explanation(attack=tuple(str(c.instance_id) for c in beyond.attackers))
    problems = verify(said, report)
    assert problems
    assert "did not evaluate" in problems[0]


def test_an_attack_among_the_ones_shown_is_fine() -> None:
    report = _combat(battlefield=("Bear",) * 5)
    shown = offered(report)[-1]
    said = Explanation(attack=tuple(str(c.instance_id) for c in shown.attackers))
    assert trusted(said, report)
