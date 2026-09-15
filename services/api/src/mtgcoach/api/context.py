"""Everything the routes share: what a server is, and what it sends.

Separate from ``app`` so that the routes there read as a list of routes. The
snapshot in particular is the single most important thing this service produces
-- it is what every client renders and what the wire contract test pins -- and
it deserves to be somewhere you can find it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from mtgcoach.api import views
from mtgcoach.api.rationing import Rationed
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.coach.report import advise
from mtgcoach.coach.table import table

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.hub import Hub
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json
    from mtgcoach.coach.advice import Explainer
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.coach.table import Table
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.rules.answer import Asker
    from mtgcoach.rules.search import RuleIndex


@dataclass(frozen=True, slots=True)
class Claude:
    """What this server can ask a model, and what it can ask about.

    Together because they are one decision -- whether this server has a Claude
    layer at all -- and because ``create_app`` had six arguments, three of them
    these.

    All three default to absent and are filled in by ``create_app``: the two
    models with the local CLI, and ``rules`` with nothing, because the
    Comprehensive Rules are an optional install and everything else works
    without them.
    """

    explainer: Explainer | None = None
    asker: Asker | None = None
    rules: RuleIndex | None = None


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
    #: Where this server's data lives, so the replay routes can find the
    #: self-play journals under it. A server built by a test has no data root
    #: and simply has no replays, which is the honest answer for one.
    data_root: Path | None = None
    #: How often and how many at once the slow routes may be asked. Per-server
    #: rather than per-module: everything else the routes need is here, two
    #: servers in one process are two servers, and a module global made one
    #: test's saturated limiter another test's mysterious 503.
    rations: Rationed = field(default_factory=Rationed)


@dataclass(frozen=True, slots=True)
class Position:
    """The board a slow answer is about, and which revision that was.

    Both slow routes need all of it and one of them needed six arguments to
    say so. Carrying the revision alongside the report is also the point of the
    thing: an answer that takes a minute has to come back saying which board it
    was about, or the client is left guessing.
    """

    report: TurnReport
    revision: int
    #: Only the rules route needs the battlefield; the turn coach's report
    #: already names every creature that matters.
    board: Table | None = None


def position(server: Server, game: Session, player: PlayerId, *, board: bool = False) -> Position:
    """Work out the board, once, for one of the slow routes."""
    return Position(
        report=advise(game.state, player, server.catalogue),
        revision=game.revision,
        board=table(game.state, player, server.catalogue) if board else None,
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
