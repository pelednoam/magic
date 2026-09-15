"""The three routes that change a game, and the one check that makes them safe.

Split from ``app`` when the seat arrived, and the seam is a real one: the
reading routes only need to know *who is asking* so they can withhold the other
hand, while these need to know it in order to refuse -- which is a different
kind of code and the part with the rule in it.

The rule: **an event may only name the seat whose token sent it.** With one
token per server, ``{"type": "draw_card", "player": "them"}`` was a sentence
either device could say about the other, and the engine had no way to disagree.
``docs/DECISIONS.md`` item 4 records that an event must say which player sent
it; this is where saying it stops being a claim.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException, WebSocket
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_403_FORBIDDEN

from mtgcoach.api.context import Seated, session, snapshot
from mtgcoach.api.eventfields import BadEventError
from mtgcoach.api.eventspec import parse
from mtgcoach.api.guard import check
from mtgcoach.api.sessions import UnknownSessionError
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import AdvanceStep

if TYPE_CHECKING:
    from collections.abc import Callable

    from fastapi import FastAPI

    from mtgcoach.api.context import Server
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json
    from mtgcoach.core.events import Event


def sent_by(event: Event, seat: str) -> None:
    """Refuse an event that names a player other than the one that sent it.

    ``AdvanceStep`` is the exception and names nobody, because ending a step is
    not a player's action: it happens when every player has passed in
    succession on an empty stack (CR 117.4), and ``core.priority`` refuses it
    until they have. So either device may send it, and neither can use it to
    get ahead of the other -- the pass it needs first is a seated event and is
    checked here like any other.

    Raises:
        HTTPException: 403 if the event names another seat. Not 400: the
            request is well formed and the engine would accept it. What is
            wrong is who sent it, and a client cannot fix that by rewriting the
            body.
    """
    if isinstance(event, AdvanceStep):
        return
    if str(event.player) != seat:
        msg = f"your token is {seat!r}; it cannot send an event for {str(event.player)!r}"
        raise HTTPException(HTTP_403_FORBIDDEN, msg)


def routes(app: FastAPI, server: Server) -> None:
    """The routes that change the game and tell everyone watching."""

    @app.post("/games/{session_id}/events", response_model=None)
    async def send_event(session_id: str, body: dict[str, object], seat: Seated) -> dict[str, Json]:
        """Apply one event, then tell everyone watching.

        The seat is checked before the engine is asked anything. An event for
        the other player is refused whether or not it would have been legal:
        "you may not do that" and "you may not do that *for them*" are
        different refusals and a player deserves the one that is true.
        """
        game = session(server, session_id)
        try:
            event = parse(body)
            sent_by(event, seat)
            check(event, game.state, server.catalogue)
            advanced = game.with_event(event)
        except (BadEventError, IllegalEventError) as refused:
            raise HTTPException(HTTP_400_BAD_REQUEST, str(refused)) from refused
        # Built before it is committed. The other order left an event stored
        # after the client had been told the request failed -- so a retry
        # applied it twice, and every later read failed the same way. The
        # sender's own board is built first, so that what it is answered with
        # exists before anything is broadcast.
        board = _boards(server, advanced)
        mine = board(seat)
        server.store.record(advanced)
        await server.hub.broadcast(session_id, board)
        return mine

    @app.post("/games/{session_id}/undo", response_model=None)
    async def undo(session_id: str, seat: Seated) -> dict[str, Json]:
        """Take back the last event. Replayed, never inverted.

        Either seat may undo, and the event it takes back may be the other
        player's. That is deliberate: undo is what the two of them do when they
        agree something was recorded wrong, it is the tracker catching up with
        a table rather than a move in the game, and a mis-tap the other player
        has to reach across for is worse than one either can fix.
        """
        undone = session(server, session_id).undone()
        board = _boards(server, undone)
        mine = board(seat)
        server.store.record(undone)
        await server.hub.broadcast(session_id, board)
        return mine

    @app.websocket("/games/{session_id}/watch")
    async def watch(websocket: WebSocket, session_id: str, seat: Seated) -> None:
        """Follow a game. Sends the board on connect, then on every change.

        The socket carries its seat for as long as it is open, so each device
        is sent its own board rather than one payload holding both hands. That
        is why the hub takes a function and not a message: two watchers of one
        game are two different payloads.
        """
        await websocket.accept()
        try:
            game = server.store.get(session_id)
        except UnknownSessionError:
            await websocket.close(code=4004, reason="no such game")
            return
        server.hub.join(session_id, websocket, seat)
        try:
            await websocket.send_json(snapshot(server, game, seat))
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


def _boards(server: Server, game: Session) -> Callable[[str], dict[str, Json]]:
    """The board for a seat, worked out once per seat and then remembered.

    One change produces up to three payloads -- the answer to the device that
    sent it and one per watching seat -- and they differ only in which hand
    they carry. Building each from scratch would advise both players twice for
    every tap; building one and sending it to everybody is what this change
    exists to stop.
    """
    made: dict[str, dict[str, Json]] = {}

    def board(seat: str) -> dict[str, Json]:
        if seat not in made:
            made[seat] = snapshot(server, game, seat)
        return made[seat]

    return board
