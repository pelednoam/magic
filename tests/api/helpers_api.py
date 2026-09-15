"""A server built out of cards written in the test, not read from a disk."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from helpers import facts
from helpers_coach import taps_for
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import Catalogue
from mtgcoach.api.context import Claude
from mtgcoach.coach.advice import ExplainerError, Explanation
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.vocabulary import TriggerEvent
from mtgcoach.rules.corpus import passages_in
from mtgcoach.rules.search import RuleIndex

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI

    from mtgcoach.coach.advice import Explainer
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.rules.answer import Answer, Asker

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
    # What each card says, as printed. Here because the rules question route
    # quotes it into the prompt and the answer checks are grounded in it -- a
    # catalogue with no text would leave both untested through the route, which
    # is the one path an answer can reach a client through.
    texts={
        "Forest": "({T}: Add {G}.)",
        "Growth": "Target creature gets +3/+3 until end of turn.",
        "Bell": "At the beginning of your upkeep, ring the bell.",
    },
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


@dataclass(slots=True)
class Answering:
    """An answerer that says what the test told it to say."""

    said: Answer

    def ask(self, question: str, briefing: str) -> Answer:
        """The prepared answer, whatever was asked."""
        del question, briefing
        return self.said


@dataclass(frozen=True, slots=True)
class NoAnswers:
    """An answerer that is never available. The default, for the same reason."""

    def ask(self, question: str, briefing: str) -> Answer:
        """Never answer.

        Raises:
            ExplainerError: Always.
        """
        del question, briefing
        msg = "no answerer in this test"
        raise ExplainerError(msg)


#: The rules excerpt, indexed once for every test that needs it. Building it is
#: a few milliseconds, but a fixture per test would pay that a hundred times.
RULES = RuleIndex.build(
    passages_in(
        (Path(__file__).resolve().parents[1] / "fixtures" / "rules_excerpt.txt").read_text(
            encoding="utf-8"
        )
    )
)


#: The token every test server uses. A fixed one rather than a fresh one so a
#: failure message shows the same string every time.
TOKEN = "token-for-tests"  # noqa: S105 - a test fixture, not a credential


def server(
    decks: Mapping[str, tuple[str, ...]] | None = None,
    explainer: Explainer | None = None,
    asker: Asker | None = None,
    rules: RuleIndex | None = None,
    data_root: Path | None = None,
) -> FastAPI:
    """An app with the small catalogue and two identical decks.

    Both models default to the ones that refuse, so no test can accidentally
    spawn a real ``claude``. ``rules`` defaults to *absent*, which is the state
    a server without the Comprehensive Rules installed is in -- a test that
    wants the question box working asks for ``RULES``. ``data_root`` defaults
    to absent too, which is a server with no journals to replay.
    """
    return create_app(
        CATALOGUE,
        DECKS if decks is None else decks,
        TOKEN,
        Claude(
            explainer=explainer if explainer is not None else NoCoach(),
            asker=asker if asker is not None else NoAnswers(),
            rules=rules,
        ),
        data_root=data_root,
    )


def talking(app: FastAPI | None = None, token: str = TOKEN) -> TestClient:
    """A test client that carries the token on every request.

    One place, because there are nearly fifty constructions of this across the
    suite and a test that forgot the header would fail with a 401 saying
    nothing about the thing it was testing. Named so it does not collide with
    the ``as client`` every caller binds it to.

    ``token`` is only passed by the tests that build a *real* server: that one
    makes its own and keeps it in a file, so the test has to read it back.
    """
    return TestClient(
        app if app is not None else server(),
        headers={"Authorization": f"Bearer {token}"},
    )
