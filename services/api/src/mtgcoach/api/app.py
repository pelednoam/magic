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

from fastapi import FastAPI, HTTPException, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_503_SERVICE_UNAVAILABLE

from mtgcoach.api.coaching import coached
from mtgcoach.api.context import Server, session, snapshot
from mtgcoach.api.dealing import library
from mtgcoach.api.eventspec import BadEventError, parse
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.api.guard import check
from mtgcoach.api.hub import Hub
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.coach.advice import ExplainerError
from mtgcoach.coach.report import advise
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import PlayerId

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.views import Json
    from mtgcoach.coach.advice import Explainer


def create_app(
    catalogue: Catalogue,
    decks: Mapping[str, tuple[str, ...]],
    explainer: Explainer | None = None,
) -> FastAPI:
    """Build the application around a set of cards and the decks it can deal.

    ``decks`` maps a deck name to the oracle ids in it, in order. Passed in
    rather than read from disk so a test can deal a three-card deck and a real
    run can deal the Beginner Box's ten.

    ``explainer`` defaults to the local ``claude`` command. Injected so that a
    test can run the whole route without a subprocess -- and so that the day
    this moves to the API, or to a different model, is a change to one caller.
    """
    server = Server(
        catalogue=catalogue,
        store=SessionStore(),
        hub=Hub(),
        decks=decks,
        explainer=explainer if explainer is not None else ClaudeCliExplainer(),
    )
    app = FastAPI(title="Magic Coach", version="0.1.0")
    # The web build is served by Metro on a different port, so every request
    # from it is cross-origin and the browser blocks it before the route is
    # ever reached -- a preflight returned 405 with no allow-origin header.
    # Open, because this is a LAN server with no credentials and no auth: there
    # is nothing here an origin check would protect, and pretending otherwise
    # would be security theatre. See PLAN.md on identity for what that costs.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    _routes(app, server)
    return app


def _routes(app: FastAPI, server: Server) -> None:
    """Attach every route.

    Split in two by whether the route changes the game, which is also the line
    between the routes that broadcast and the routes that do not.
    """
    _reading(app, server)
    _playing(app, server)


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
    def new_game(body: dict[str, str]) -> dict[str, Json]:
        """Start a game between two decks."""
        libraries = {
            PlayerId(name): library(server.decks, name, body.get(name, ""))
            for name in ("you", "them")
        }
        try:
            started = server.store.create(libraries, PlayerId("you"))
        except ValueError as refused:
            # A deck too short to draw an opening hand. `serve` drops cards the
            # store does not have, so a partial import can advertise a deck of
            # six -- which is a thing to say, not a stack trace.
            raise HTTPException(HTTP_400_BAD_REQUEST, str(refused)) from refused
        return {"session_id": started.session_id, **snapshot(server, started)}

    @app.get("/games/{session_id}", response_model=None)
    def read_game(session_id: str) -> dict[str, Json]:
        """The board and the advice, as they stand."""
        return snapshot(server, session(server, session_id))


def _playing(app: FastAPI, server: Server) -> None:  # noqa: C901 - one route each, no branching
    """The routes that change the game, or take a minute to answer."""

    @app.post("/games/{session_id}/events", response_model=None)
    async def send_event(session_id: str, body: dict[str, object]) -> dict[str, Json]:
        """Apply one event, then tell everyone watching."""
        game = session(server, session_id)
        try:
            event = parse(body)
            check(event, game.state, server.catalogue)
            advanced = game.with_event(event)
        except (BadEventError, IllegalEventError) as refused:
            raise HTTPException(HTTP_400_BAD_REQUEST, str(refused)) from refused
        # Built before it is committed. The other order left an event stored
        # after the client had been told the request failed -- so a retry
        # applied it twice, and every later read failed the same way.
        board = snapshot(server, advanced)
        server.store.record(advanced)
        await server.hub.broadcast(session_id, board)
        return board

    @app.post("/games/{session_id}/undo", response_model=None)
    async def undo(session_id: str) -> dict[str, Json]:
        """Take back the last event. Replayed, never inverted."""
        undone = session(server, session_id).undone()
        board = snapshot(server, undone)
        server.store.record(undone)
        await server.hub.broadcast(session_id, board)
        return board

    # Deliberately not `async def`. Asking the coach is a subprocess that can
    # take a minute, and an async route would hold the event loop for all of
    # it -- freezing every other player's socket. FastAPI runs a plain `def`
    # in a threadpool, which is exactly the behaviour wanted here.
    @app.post("/games/{session_id}/coach", response_model=None)
    def coach(session_id: str, body: dict[str, str]) -> dict[str, Json]:
        """Ask Claude what to do about this player's turn."""
        game = session(server, session_id)
        player = PlayerId(body.get("player", "you"))
        if player not in game.state.players:
            raise HTTPException(HTTP_400_BAD_REQUEST, f"no player {player}")
        try:
            return coached(server.explainer, advise(game.state, player, server.catalogue))
        except ExplainerError as unavailable:
            # Not a server fault and not fatal: the deterministic panel is
            # already on screen and already right. 503 says "try again", which
            # is the truth about a flaky subprocess.
            raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, str(unavailable)) from unavailable

    @app.websocket("/games/{session_id}/watch")
    async def watch(websocket: WebSocket, session_id: str) -> None:
        """Follow a game. Sends the board on connect, then on every change."""
        await websocket.accept()
        try:
            game = server.store.get(session_id)
        except UnknownSessionError:
            await websocket.close(code=4004, reason="no such game")
            return
        server.hub.join(session_id, websocket)
        try:
            await websocket.send_json(snapshot(server, game))
            while True:
                # The raw message, not `receive_text()`: that raised KeyError
                # on a binary frame, taking the handler down rather than the
                # connection. The socket is one-way, so whatever a client sends
                # is a keep-alive -- except a disconnect, which arrives here as
                # a message and ends the loop. `finally` cleans up either way,
                # so there is no `except WebSocketDisconnect` left to write.
                message = await websocket.receive()
                if message["type"] == "websocket.disconnect":
                    break
        finally:
            server.hub.leave(session_id, websocket)
