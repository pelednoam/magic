"""The HTTP and WebSocket surface. Thin on purpose.

Every decision in here has been made somewhere testable already: events are
parsed by ``eventspec``, checked by ``guard``, reduced by ``core``, advised on
by ``coach``, rendered by ``views`` and assembled by ``context``. What is left
is routing and status codes.

The server holds the authoritative game (§4). Clients send events and are told
what happened; they do not compute anything, which is what lets the phone, the
tablet and the laptop be three views of one game rather than three games.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST

from mtgcoach.api import acting, thinking, walking
from mtgcoach.api.asker import ClaudeCliAsker
from mtgcoach.api.context import Claude, Seated, Server, session, snapshot
from mtgcoach.api.dealing import library
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.api.gatekeeper import guarded
from mtgcoach.api.hub import Hub
from mtgcoach.api.seating import SEATS
from mtgcoach.api.sessions import SessionStore
from mtgcoach.api.sources import Sources
from mtgcoach.core.ids import PlayerId
from mtgcoach.core.revision import engine

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from fastapi import FastAPI

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.seating import Seating
    from mtgcoach.api.views import Json


def create_app(
    catalogue: Catalogue,
    decks: Mapping[str, tuple[str, ...]],
    seating: Seating,
    claude: Claude | None = None,
    data_root: Path | None = None,
) -> FastAPI:
    """Build the application around a set of cards and the decks it can deal.

    ``decks`` maps a deck name to the oracle ids in it, in order. Passed in
    rather than read from disk so a test can deal a three-card deck and a real
    run can deal the Beginner Box's ten.

    ``claude`` carries the two models and the rules index; see ``context.Claude``.

    ``data_root`` is where the self-play journals live, for the replay routes.
    Optional, because a test server has none and honestly has no replays.

    ``seating`` is one token per seat and is required. There is deliberately no
    open mode and no shared secret: an argument that can be left out is an
    argument that gets left out, and this one is the whole of the server's
    access control. ``Seating`` refuses to exist without a usable token for
    every seat, so there is nothing left for this function to check.
    """
    asked = claude if claude is not None else Claude()
    server = Server(
        catalogue=catalogue,
        store=SessionStore(),
        hub=Hub(),
        decks=decks,
        explainer=asked.explainer if asked.explainer is not None else ClaudeCliExplainer(),
        asker=asked.asker if asked.asker is not None else ClaudeCliAsker(),
        rules=asked.rules,
        # Worked out here rather than passed in: two of the three are already
        # in this function's arguments, and a revision a caller could get
        # wrong is worse than no revision at all.
        sources=Sources(engine=engine(), cards=catalogue.revision, rules=asked.rules_revision),
        data_root=data_root,
    )
    app = guarded(seating)
    _routes(app, server)
    return app


def _routes(app: FastAPI, server: Server) -> None:
    """Attach every route.

    Three groups: the ones that only look, the ones that change the game and
    broadcast, and the two that ask Claude and take a minute over it.
    """
    _reading(app, server)
    acting.routes(app, server)
    thinking.routes(app, server)
    walking.routes(app, server)


def _named(seat: str) -> tuple[str, str]:
    """This seat and the other one, in that order.

    A two-player game, so "the other one" is the other member of ``SEATS``.
    Here rather than inline so that the route reads as the rule it is applying
    -- the deck a device calls "mine" is dealt to the seat its token names.
    """
    other = next(one for one in SEATS if one != seat)
    return seat, other


def _reading(app: FastAPI, server: Server) -> None:
    """The routes that only look.

    Every route says ``response_model=None``. The JSON these return is built by
    ``views``, deliberately and by hand, and that is the contract; letting
    FastAPI infer a pydantic model from the annotation would put a second,
    generated contract in front of it -- and it cannot build one anyway, because
    ``Json`` is recursive.
    """

    @app.get("/decks", response_model=None)
    def list_decks() -> dict[str, Json]:
        """The decks this server can deal."""
        return {"decks": sorted(server.decks)}

    @app.post("/games", response_model=None)
    def new_game(body: dict[str, str], seat: Seated) -> dict[str, Json]:
        """Start a game between two decks, named from the asking device's side.

        ``{"mine": ..., "theirs": ...}``, and **this** decides which seat each
        deck reaches. The body used to name the seats -- ``{"you": ...,
        "them": ...}`` -- which worked only while the device that started a
        game was always seat "you". It is not, now that a seat comes off a
        token: a phone holding the other one picked its own deck and the server
        dealt that deck to its opponent, so it played the whole game out of the
        deck it had chosen *for* them.

        The client cannot fix that for itself without doing the seat
        arithmetic, and deciding which player gets which deck is a setup rule.
        §4 has the app render and the server decide, so the names on the wire
        are relative and this is where they are resolved.

        Either seat may start a game. Whoever presses the button is not thereby
        the first player: the deal decides that, and decides it the same way
        whichever device asked.
        """
        mine, theirs = _named(seat)
        libraries = {
            PlayerId(mine): library(server.decks, mine, body.get("mine", "")),
            PlayerId(theirs): library(server.decks, theirs, body.get("theirs", "")),
        }
        try:
            started = server.store.create(libraries, PlayerId(SEATS[0]))
        except ValueError as refused:
            # A deck too short to draw an opening hand. `serve` drops cards the
            # store does not have, so a partial import can advertise a deck of
            # six -- which is a thing to say, not a stack trace.
            raise HTTPException(HTTP_400_BAD_REQUEST, str(refused)) from refused
        return {"session_id": started.session_id, **snapshot(server, started, seat)}

    @app.get("/games/{session_id}", response_model=None)
    def read_game(session_id: str, seat: Seated) -> dict[str, Json]:
        """The board and the advice, as they stand, for the seat that asked."""
        return snapshot(server, session(server, session_id), seat)
