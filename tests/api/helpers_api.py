"""A server built out of cards written in the test, not read from a disk."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helpers import facts
from helpers_coach import taps_for
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import Catalogue
from mtgcoach.coach.advice import ExplainerError, Explanation
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.vocabulary import TriggerEvent

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI

    from mtgcoach.coach.advice import Explainer
    from mtgcoach.coach.report import TurnReport

FOREST = facts("Forest", land=True)
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
GROWTH = facts("Giant Growth", "{G}", instant=True)

#: A creature whose ability fires on the clock, so the coach has a reminder to
#: give. Without one, no payload ever carries a `reminders` entry.
BELL = facts("Bell-Ringer", "{1}{W}", power=1, toughness=3, creature=True)
RINGS = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())

#: A catalogue small enough to read, with one card of each kind that matters.
CATALOGUE = Catalogue(
    cards={"Forest": FOREST, "Bear": BEAR, "Growth": GROWTH, "Bell": BELL},
    # An entry, even an empty one, is the fixture saying "I know this card".
    rules={"Forest": (taps_for("{G}"),), "Bell": (RINGS,), "Bear": (), "Growth": ()},
)

#: The opening seven are the first seven, so this is what a test will be
#: holding: five Forests, a Bear and a trick. Enough to play a land, cast the
#: creature next turn, and keep a card that cannot be cast yet.
GREEN = (
    "Forest",
    "Forest",
    "Forest",
    "Bear",
    "Bell",
    "Growth",
    "Forest",
    "Forest",
    "Forest",
    "Bear",
)
DECKS: Mapping[str, tuple[str, ...]] = {"green": GREEN, "other": GREEN}


@dataclass(slots=True)
class Canned:
    """An explainer that says what the test told it to say.

    Mutable, because an instance id only exists once a game has been dealt --
    so a test that recommends a real card has to start the game, read the hand,
    and only then decide what the coach will say about it.
    """

    said: Explanation

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """The prepared answer, whatever was asked."""
        del report, briefing
        return self.said


@dataclass(frozen=True, slots=True)
class NoCoach:
    """An explainer that is never available. The default, deliberately.

    Every test gets this unless it asks for something else, so no test can
    accidentally spawn a real ``claude`` -- which would be slow, would cost
    quota, and would pass or fail for reasons nothing in the repository
    controls.
    """

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """Never answer.

        Raises:
            ExplainerError: Always.
        """
        del report, briefing
        msg = "no coach in this test"
        raise ExplainerError(msg)


def server(
    decks: Mapping[str, tuple[str, ...]] | None = None,
    explainer: Explainer | None = None,
) -> FastAPI:
    """An app with the small catalogue and two identical decks."""
    return create_app(
        CATALOGUE,
        DECKS if decks is None else decks,
        explainer if explainer is not None else NoCoach(),
    )
