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

from fastapi import HTTPException, WebSocket
from starlette.status import HTTP_400_BAD_REQUEST

from mtgcoach.api import thinking, walking
from mtgcoach.api.access import MissingTokenError
from mtgcoach.api.asker import ClaudeCliAsker
from mtgcoach.api.context import Claude, Server, session, snapshot
from mtgcoach.api.dealing import library
from mtgcoach.api.eventspec import BadEventError, parse
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.api.gatekeeper import guarded
from mtgcoach.api.guard import check
from mtgcoach.api.hub import Hub
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import PlayerId

if TYPE_CHECKING:
    from collections.abc import Mapping
    from pathlib import Path

    from fastapi import FastAPI

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.views import Json


def create_app(
    catalogue: Catalogue,
    decks: Mapping[str, tuple[str, ...]],
    token: str,
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

    ``token`` is required and may not be empty. There is deliberately no open
    mode: an argument that can be left out is an argument that gets left out,
    and this one is the whole of the server's access control.

    Raises:
        MissingTokenError: If ``token`` is empty.
    """
    if not token:
        msg = "a server needs a token; there is no open mode. See api.access."
        raise MissingTokenError(msg)
    asked = claude if claude is not None else Claude()
    server = Server(
        catalogue=catalogue,
        store=SessionStore(),
        hub=Hub(),
        decks=decks,
        explainer=asked.explainer if asked.explainer is not None else ClaudeCliExplainer(),
        asker=asked.asker if asked.asker is not None else ClaudeCliAsker(),
        rules=asked.rules,
        data_root=data_root,
    )
    app = guarded(token)
    _routes(app, server)
    return app


def _routes(app: FastAPI, server: Server) -> None:
    """Attach every route.

    Three groups: the ones that only look, the ones that change the game and
    broadcast, and the two that ask Claude and take a minute over it.
    """
    _reading(app, server)
    _playing(app, server)
    thinking.routes(app, server)
    walking.routes(app, server)


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


def _playing(app: FastAPI, server: Server) -> None:
    """The routes that change the game and broadcast the result."""

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
