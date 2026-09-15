"""The panel that tells a player what fired, and when.

Split from `test_briefing` because the panel has two kinds in it now and the
difference is the whole point: a clock trigger is happening *now*, an arrival
trigger fired when the card was put down and what is being asked is whether it
was resolved.

It said "TRIGGERS NOW" and could only ever report the first kind -- and the
Beginner Box has none of those, so it was empty for every real board through
two milestones.
"""

from __future__ import annotations

from dataclasses import replace

from helpers import ME, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.briefing import brief
from mtgcoach.coach.report import advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
BOOK = Book(cards={"Forest": FOREST, "Bear": BEAR}, rules={"Forest": FOREST_RULES, "Bear": ()})


def _flat(text: str) -> str:
    """The prompt with its line wrapping removed."""
    return " ".join(text.split())


def test_an_arrival_trigger_is_named_with_when_it_fired() -> None:
    """The panel said "TRIGGERS NOW", which is not true of an arrival trigger.

    That one fired when the card was put down, and what is being asked is
    whether it was resolved -- so the moment is attached to each name rather
    than asserted once in the heading.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    book = Book(
        cards={**BOOK.cards, "Elite": facts("Elite", creature=True, power=2, toughness=2)},
        rules={**BOOK.rules, "Elite": (entering,)},
    )
    state = game(battlefield=("Elite",))
    mine = state.player(ME)
    fresh = state.with_player(
        ME,
        replace(mine, battlefield=(replace(mine.battlefield[0], entered_on_turn=state.turn),)),
    )
    text = _flat(brief(advise(fresh, ME, book)))
    assert "TRIGGERS TO HANDLE" in text
    assert "Elite (when it came onto the battlefield)" in text


def test_a_watcher_is_named_with_what_set_it_off() -> None:
    """The two arrival shapes are not the same permanent.

    "Whenever another creature enters" sits on something already here, so the
    moment to report is somebody *else's* arrival -- and telling the player it
    fired "when it came onto the battlefield" would point at the wrong card.
    """
    watching = TriggeredAbility(Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS), ())
    book = Book(
        cards={
            **BOOK.cards,
            "Watcher": facts("Watcher", creature=True, power=1, toughness=1),
            "Newcomer": facts("Newcomer", creature=True, power=1, toughness=1),
        },
        rules={**BOOK.rules, "Watcher": (watching,), "Newcomer": ()},
    )
    state = game(battlefield=("Watcher", "Newcomer"))
    mine = state.player(ME)
    watcher, newcomer = mine.battlefield
    fresh = state.with_player(
        ME,
        replace(
            mine,
            battlefield=(
                replace(watcher, entered_on_turn=0),
                replace(newcomer, entered_on_turn=state.turn),
            ),
        ),
    )
    text = _flat(brief(advise(fresh, ME, book)))
    assert "Watcher (when the other creature arrived)" in text


def test_triggers_are_named() -> None:
    rings = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())
    book = Book(
        cards={**BOOK.cards, "Bell": facts("Bell", creature=True, power=1, toughness=1)},
        rules={**BOOK.rules, "Bell": (rings,)},
    )
    state = game(battlefield=("Bell",), step=Step.UPKEEP)
    text = _flat(brief(advise(state, ME, book)))
    assert "TRIGGERS TO HANDLE (name every one of these in your answer): Bell" in text
    assert "(now, at this step)" in text, "a clock trigger is happening right now"
    # The instruction and the check were added a round apart, and the checker
    # demanded this before the prompt ever asked for it -- which would have
    # refused every turn with a trigger on the table.
    assert "must be named somewhere in your answer" in text


def test_a_turn_with_no_triggers_says_nothing_about_them() -> None:
    """The section, not the word -- rule 4 names it whether or not any fired.

    Asserting on the old heading here would have gone quietly vacuous the
    moment the heading changed, which is exactly what happened.
    """
    assert "TRIGGERS TO HANDLE (name" not in brief(advise(game(), ME, BOOK))
