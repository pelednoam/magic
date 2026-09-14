"""The checks about silence, and the one about holding back.

A model that says nothing about a trigger that is firing, or about a card the
engine cannot read, is indistinguishable from one that decided it did not
matter -- and a beginner reads silence as "counted". So those are checks on
what is *missing* from the words, which makes them a different shape from the
checks on the choice, and worth reading together.

Holding back is here for the opposite reason: it looked like an absence and is
a recommendation, which is why it was going unchecked.
"""

from __future__ import annotations

from helpers import ME, UNKNOWN_ABILITY, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.advice import Explanation, trusted, verify
from mtgcoach.coach.checks import offered
from mtgcoach.coach.report import TurnReport, advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
RINGS = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())
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


def _upkeep() -> TurnReport:
    """An upkeep with a trigger on the table and nothing else to do."""
    book = Book(
        cards={"Bell": facts("Bell-Ringer", "{1}{W}", power=1, toughness=3, creature=True)},
        rules={"Bell": (RINGS,)},
    )
    report = advise(game(battlefield=("Bell",), step=Step.UPKEEP), ME, book)
    assert report.reminders, "the fixture must actually have a trigger on it"
    return report


def test_passing_the_turn_over_a_firing_trigger_is_refused() -> None:
    """Stopping the shortcut doing this was only half of it.

    The model was then asked, and nothing made it mention the trigger either --
    so the same wrong answer came back the long way round, marked trusted.
    """
    said = Explanation(because="Nothing to do.", in_short="Pass the turn.")
    problems = verify(said, _upkeep())
    assert problems
    assert "Bell-Ringer" in problems[0]


def test_naming_the_trigger_anywhere_is_enough() -> None:
    """A check on silence, not on where a model chose to put the sentence."""
    report = _upkeep()
    assert trusted(Explanation(in_short="Your Bell-Ringer goes off now."), report)
    assert trusted(Explanation(because="x", watch_out=("Bell-Ringer triggers",)), report)
    assert trusted(Explanation(because="x", check_yourself=("Bell-Ringer",)), report)


def test_the_trigger_check_does_not_mind_case() -> None:
    assert trusted(Explanation(in_short="your bell-ringer goes off"), _upkeep())


# --- holding back is a recommendation, and it is checked like one -------------


def test_attacking_with_nobody_matches_the_plan_that_says_so() -> None:
    """The engine costs holding back like any other plan, so it is checked."""
    report = _combat(battlefield=("Bear",))
    assert any(not plan.attackers for plan in offered(report)), "holding back is a plan"
    assert trusted(Explanation(attack=()), report)


def test_saying_nothing_about_combat_outside_combat_is_fine() -> None:
    assert trusted(Explanation(attack=()), _main())


# --- the words must not recommend what the choice did not ---------------------


def test_prose_recommending_an_unplayable_card_is_refused() -> None:
    """The words a person reads are not the fields that were checked.

    `play` and `attack` are checked exactly; the sentences beside them are what
    somebody actually reads, and nothing made the two agree. A model that left
    `play` empty and wrote "cast the Dragon" was marked trusted and showed
    "cast the Dragon". Natural language cannot be checked in general, so this
    checks the one case that is common and unambiguous: prose naming a card in
    this hand that the engine says cannot be played.
    """
    report = _main(hand=("Bear",))
    (bear,) = report.hand
    assert not bear.playable, "the fixture must have an uncastable card in hand"
    said = Explanation(in_short="Cast the Grizzly Bears!", because="It is the best play.")
    problems = verify(said, report)
    assert problems
    assert "cannot be played" in problems[-1]


def test_prose_about_the_card_it_does_recommend_is_fine() -> None:
    report = _main(hand=("Forest", "Bear"))
    forest = next(card for card in report.hand if card.playable)
    said = Explanation(
        play=str(forest.instance_id),
        in_short="Put down a Forest.",
        because="A land is free.",
    )
    assert trusted(said, report)


def test_check_yourself_may_name_an_unplayable_card() -> None:
    """The honesty check requires it, so this must not refuse it.

    Reading `check_yourself` as advice prose made the two checks contradict
    each other: an explanation had to name the card and was refused for it.
    """
    book = Book(
        cards={**BOOK.cards, "Puzzle": facts("Puzzle", "{2}{U}")},
        rules={**BOOK.rules, "Puzzle": (UNKNOWN_ABILITY,)},
    )
    report = advise(game(hand=("Puzzle",)), ME, book)
    assert trusted(Explanation(check_yourself=("Puzzle: I cannot read this one",)), report)
