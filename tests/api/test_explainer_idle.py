"""Turns the coach answers without asking anybody.

Most of a game is a step with no choice in it, and asking a model "which of
these zero options is best" costs a subprocess and a quota call to be told what
the report already says. The shortcut that avoids it is also the one place in
this layer that can be confidently wrong without a model being involved, which
is why it is tested this closely.
"""

from __future__ import annotations

from fakeprocess import Never
from helpers import ME, UNKNOWN_ABILITY, facts
from helpers_coach import Book, game
from mtgcoach.coach.report import advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent
from test_explainer import BOOK, FOREST, FOREST_RULES
from test_explainer_cli import envelope_answer, explain

#: A creature whose ability fires on the clock, so a turn has a reminder on it.
RINGS = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())


def test_an_empty_turn_is_answered_without_asking() -> None:
    """Most of a game is steps with no choice. Those cost nothing."""
    got = explain(Never(), advise(game(), ME, BOOK))
    assert "pass the turn" in got.in_short
    assert got.play == ""


def test_a_turn_with_an_unmodelled_card_is_still_asked_about() -> None:
    """The engine could not speak for it, so somebody has to."""
    book = Book(
        cards={"Forest": FOREST, "Odd": facts("Odd Thing", "{1}")},
        rules={"Forest": FOREST_RULES, "Odd": (UNKNOWN_ABILITY,)},
    )
    report = advise(game(battlefield=("Odd",)), ME, book)
    assert report.unknown
    fake = envelope_answer()
    assert explain(fake, report).play == "abc"
    assert fake.stdin == "the briefing"


def test_a_pending_trigger_is_not_a_turn_with_nothing_in_it() -> None:
    """The shortcut used to say "pass the turn" over a trigger that was firing.

    An upkeep with a trigger has no playable card and no attack plan, so the
    no-decision shortcut fired -- while the reminder panel two inches away said
    the trigger was happening now. Telling a nine-year-old to pass through
    their own trigger is the confidently wrong answer this whole layer exists
    to prevent, and it came from the half of it that asks no model anything.
    """
    book = Book(
        cards={"Bell": facts("Bell-Ringer", "{1}{W}", power=1, toughness=3, creature=True)},
        rules={"Bell": (RINGS,)},
    )
    report = advise(game(battlefield=("Bell",), step=Step.UPKEEP), ME, book)
    assert report.reminders, "the fixture must actually have a trigger on it"
    fake = envelope_answer()
    assert explain(fake, report).play == "abc"
    assert fake.stdin == "the briefing"
