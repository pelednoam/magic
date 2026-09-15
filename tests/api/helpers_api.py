"""A server built out of cards written in the test, not read from a disk.

The models it is built with live in ``helpers_fakes``: this module says what a
test *server* is made of, that one says what stands in for the two things this
project asks a model. ``driving`` is the third of the set -- how a test drives
what this builds.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from helpers import facts
from helpers_coach import taps_for
from helpers_fakes import NoAnswers, NoCoach
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import Catalogue
from mtgcoach.api.context import Claude
from mtgcoach.api.seating import SEATS, Seating
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.vocabulary import TriggerEvent
from mtgcoach.rules.corpus import passages_in
from mtgcoach.rules.search import RuleIndex

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI

    from mtgcoach.coach.advice import Explainer
    from mtgcoach.rules.answer import Asker

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


#: The rules excerpt, indexed once for every test that needs it: a fixture per
#: test would pay those few milliseconds a hundred times.
RULES = RuleIndex.build(
    passages_in(
        (Path(__file__).resolve().parents[1] / "fixtures" / "rules_excerpt.txt").read_text(
            encoding="utf-8"
        )
    )
)


#: The token for the seat a test plays from, and the one for the other device.
#: Fixed rather than fresh, so a failure message shows the same string every
#: time. Two of them, because one for both seats is the arrangement a token per
#: seat exists to replace.
TOKEN = "token-for-tests"  # noqa: S105 - a test fixture, not a credential
OTHER_TOKEN = "token-for-the-other-seat"  # noqa: S105 - a test fixture

#: One token per seat, in ``seating.SEATS`` order, and what to call each seat.
SEATING = Seating({SEATS[0]: TOKEN, SEATS[1]: OTHER_TOKEN})
MINE, THEIRS = SEATS


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
        SEATING,
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

    ``token`` defaults to ``MINE``'s, the seat almost every test plays from.
    It is passed by the tests that need the other device -- ``OTHER_TOKEN`` --
    and by the ones that build a *real* server, which makes its own tokens and
    keeps them in a file, so the test has to read them back.
    """
    return TestClient(
        app if app is not None else server(),
        headers={"Authorization": f"Bearer {token}"},
    )
