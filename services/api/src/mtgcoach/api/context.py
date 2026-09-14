"""Everything the routes share: what a server is, and what it sends.

Separate from ``app`` so that the routes there read as a list of routes. The
snapshot in particular is the single most important thing this service produces
-- it is what every client renders and what the wire contract test pins -- and
it deserves to be somewhere you can find it.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from mtgcoach.api import views
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.coach.report import advise

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.hub import Hub
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json
    from mtgcoach.coach.advice import Explainer
    from mtgcoach.rules.answer import Asker
    from mtgcoach.rules.search import RuleIndex


#: How many of the two slow routes may be in flight at once. The threadpool
#: has ten workers by default and the tracker's own routes need some of them,
#: so the slow ones get a minority of it.
MAX_IN_FLIGHT = 3


@dataclass(slots=True)
class Server:
    """Everything the routes need, in one place they can be given in a test."""

    catalogue: Catalogue
    store: SessionStore
    hub: Hub
    decks: Mapping[str, tuple[str, ...]]
    explainer: Explainer
    asker: Asker
    #: None when the Comprehensive Rules are not installed. The rules question
    #: route then says so, and everything else works exactly as before -- the
    #: tracker and the turn coach do not need the rules document.
    rules: RuleIndex | None
    #: How many slow asks this server will run at once. Per-server rather than
    #: per-module: everything else the routes need is here, two servers in one
    #: process are two servers, and a module global made one test's saturated
    #: limiter another test's mysterious 503.
    in_flight: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(MAX_IN_FLIGHT)
    )


def session(server: Server, session_id: str) -> Session:
    """The game, or a 404."""
    try:
        return server.store.get(session_id)
    except UnknownSessionError as missing:
        raise HTTPException(HTTP_404_NOT_FOUND, "no such game") from missing


def snapshot(server: Server, game: Session) -> dict[str, Json]:
    """The board, plus what each player can do about it.

    Advice for *both* players in one payload: the tracker is one screen at a
    kitchen table, and the person defending needs the block advice as much as
    the attacker needs the attack advice.
    """
    return {
        # How many times this game has changed. The client uses it to ignore a
        # stale reply: an HTTP response and a broadcast race, and without an
        # ordering the older of the two could permanently roll the board back.
        # It counts *changes*, not events -- undo is a change that removes one,
        # so counting events made this go backwards and the client threw away
        # every undo.
        "version": game.revision,
        # Whether this server can answer rules questions at all. The document
        # is an optional install, and without it the app used to show a question
        # box, let somebody type a question, and only then say the feature was
        # off. A flag costs one boolean and moves that sentence to the top.
        "rules_available": server.rules is not None,
        "state": views.state(game.state, server.catalogue.name),
        "advice": {
            str(player): views.report(advise(game.state, player, server.catalogue))
            for player in game.state.players
        },
    }
