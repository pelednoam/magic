"""The HTTP and WebSocket surface. Thin on purpose.

Every decision in here has been made somewhere testable already: events are
parsed by ``eventspec``, checked by ``guard``, reduced by ``core``, advised on
by ``coach`` and rendered by ``views``. What is left is routing, status codes,
and a socket -- so that is all this file contains, and it is short enough to
read in one sitting.

The server holds the authoritative game (§4). Clients send events and are told
what happened; they do not compute anything, which is what lets the phone, the
tablet and the laptop be three views of one game rather than three games.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_404_NOT_FOUND

from mtgcoach.api import views
from mtgcoach.api.eventspec import BadEventError, parse
from mtgcoach.api.guard import check
from mtgcoach.api.hub import Hub
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.coach.report import advise
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json


@dataclass(slots=True)
class Server:
    """Everything the routes need, in one place they can be given in a test."""

    catalogue: Catalogue
    store: SessionStore
    hub: Hub
    decks: Mapping[str, tuple[str, ...]]


def create_app(catalogue: Catalogue, decks: Mapping[str, tuple[str, ...]]) -> FastAPI:
    """Build the application around a set of cards and the decks it can deal.

    ``decks`` maps a deck name to the oracle ids in it, in order. Passed in
    rather than read from disk so a test can deal a three-card deck and a real
    run can deal the Beginner Box's ten.
    """
    server = Server(catalogue=catalogue, store=SessionStore(), hub=Hub(), decks=decks)
    app = FastAPI(title="Magic Coach", version="0.1.0")
    _routes(app, server)
    return app


def _routes(app: FastAPI, server: Server) -> None:  # noqa: C901 - one route each, no branching
    """Attach every route. Split out so ``create_app`` reads as a list of them.

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
            PlayerId(name): _library(server, name, body.get(name, "")) for name in ("you", "them")
        }
        session = server.store.create(libraries, PlayerId("you"))
        return {"session_id": session.session_id, **_snapshot(server, session)}

    @app.get("/games/{session_id}", response_model=None)
    def read_game(session_id: str) -> dict[str, Json]:
        """The board and the advice, as they stand."""
        return _snapshot(server, _session(server, session_id))

    @app.post("/games/{session_id}/events", response_model=None)
    async def send_event(session_id: str, body: dict[str, object]) -> dict[str, Json]:
        """Apply one event, then tell everyone watching."""
        session = _session(server, session_id)
        try:
            event = parse(body)
            check(event, session.state, server.catalogue)
            session = server.store.record(session.with_event(event))
        except (BadEventError, IllegalEventError) as refused:
            raise HTTPException(HTTP_400_BAD_REQUEST, str(refused)) from refused
        snapshot = _snapshot(server, session)
        await server.hub.broadcast(session_id, snapshot)
        return snapshot

    @app.post("/games/{session_id}/undo", response_model=None)
    async def undo(session_id: str) -> dict[str, Json]:
        """Take back the last event. Replayed, never inverted."""
        session = server.store.record(_session(server, session_id).undone())
        snapshot = _snapshot(server, session)
        await server.hub.broadcast(session_id, snapshot)
        return snapshot

    @app.websocket("/games/{session_id}/watch")
    async def watch(websocket: WebSocket, session_id: str) -> None:
        """Follow a game. Sends the board on connect, then on every change."""
        await websocket.accept()
        try:
            session = server.store.get(session_id)
        except UnknownSessionError:
            await websocket.close(code=4004, reason="no such game")
            return
        server.hub.join(session_id, websocket)
        try:
            await websocket.send_json(_snapshot(server, session))
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            server.hub.leave(session_id, websocket)


def _library(server: Server, player: str, deck: str) -> tuple[CardInstance, ...]:
    """Deal one player their deck, giving every card its own identity."""
    if deck not in server.decks:
        raise HTTPException(HTTP_400_BAD_REQUEST, f"unknown deck {deck!r}")
    return tuple(
        CardInstance(InstanceId(f"{player}-{index}"), OracleId(oracle))
        for index, oracle in enumerate(server.decks[deck])
    )


def _session(server: Server, session_id: str) -> Session:
    """The game, or a 404."""
    try:
        return server.store.get(session_id)
    except UnknownSessionError as missing:
        raise HTTPException(HTTP_404_NOT_FOUND, "no such game") from missing


def _snapshot(server: Server, session: Session) -> dict[str, Json]:
    """The board, plus what each player can do about it.

    Advice for *both* players in one payload: the tracker is one screen at a
    kitchen table, and the person defending needs the block advice as much as
    the attacker needs the attack advice.
    """
    return {
        "state": views.state(session.state, server.catalogue.name),
        "advice": {
            str(player): views.report(advise(session.state, player, server.catalogue))
            for player in session.state.players
        },
    }
