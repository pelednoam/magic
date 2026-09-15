"""Everything the routes share: what a server is, and what it sends.

Separate from ``app`` so that the routes there read as a list of routes. The
snapshot in particular is the single most important thing this service produces
-- it is what every client renders and what the wire contract test pins -- and
it deserves to be somewhere you can find it.

``seats`` holds the other thing they all share: reading the seat off a
connection, and deciding whether that seat plays in this game. Both were here
and grew this module past the line limit, which was the nudge -- they really
are a different subject. The ``Seated`` alias the routes declare stays here;
see ``seats`` for why.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Annotated

from fastapi import Depends, HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from mtgcoach.api import boardview, views
from mtgcoach.api.rationing import Rationed
from mtgcoach.api.seats import seated, seated_in
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.api.sources import Sources
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
    #: Which revision the document in ``rules`` is -- its own "effective as of"
    #: sentence, read by ``rules.effective``. Here because it belongs to that
    #: document and travels with it; ``Server.sources`` is where it is used.
    #: Empty when no rules are installed, which is a supported way to run this.
    rules_revision: str = ""


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
    #: Which engine, card data and rules this server is playing under. Sent
    #: with every board and recorded on every game: a journal that says only
    #: what happened cannot say what it happened *under*, and that is what made
    #: a directory of them unreadable rather than merely old. See ``sources``.
    sources: Sources = field(default_factory=Sources)
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


#: A route's way of asking who is talking to it: ``seat: Seated`` in the
#: signature, and the answer comes from the token rather than the payload.
#:
#: A plain assignment rather than a ``type`` alias: FastAPI reads the
#: annotation to find the ``Depends`` in it, and a lazily-evaluated alias hides
#: it -- the route would then have an undeclared body parameter called "seat",
#: which is a 422 on every request rather than an error anybody can see.
#:
#: Here rather than beside ``seated`` in ``seats``, because every route module
#: imports this one at runtime already; see that module's docstring.
Seated = Annotated[str, Depends(seated)]


def session(server: Server, session_id: str) -> Session:
    """The game, or a 404."""
    try:
        return server.store.get(session_id)
    except UnknownSessionError as missing:
        raise HTTPException(HTTP_404_NOT_FOUND, "no such game") from missing


def snapshot(server: Server, game: Session, seat: str) -> dict[str, Json]:
    """The board, plus what this seat can do about it.

    One seat's payload, and ``seat`` comes from the token the request carried
    (``gatekeeper.seat_of``). It used to carry advice for *both* players --
    "the tracker is one screen at a kitchen table" -- and a turn report names
    every card in the hand it is about, so that sentence was the opponent's
    hand arriving on both devices twice over: once in the board and once in the
    advice. Both halves are one seat's now.

    Each device still gets what it needs to play its own side, because each
    device has its own token. What is gone is a single screen showing both
    hands, which the rules do not allow anybody to see (CR 400.2) and which a
    child learning from this app must not be shown.

    Raises:
        HTTPException: 403 if this seat is not a player in this game; see
            ``seated_in``.
    """
    player = seated_in(game, seat)
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
        # Which engine, card data and rules this board was produced under. On
        # the wire because a client showing a position should be able to say
        # what produced it -- and because a recorded game carries the same
        # three, so the two can be compared at all.
        "sources": {
            "engine": server.sources.engine,
            "cards": server.sources.cards,
            "rules": server.sources.rules,
        },
        # Which seat this payload is for, so the app does not have to be told
        # and cannot be told wrong. It used to be chosen on the device -- start
        # a game and you were "you", join one and you were "them" -- and a
        # device set to the wrong seat was a device acting as the other player.
        "seat": seat,
        "state": boardview.state(game.state, server.catalogue, seat),
        "advice": {seat: views.report(advise(game.state, player, server.catalogue))},
    }
