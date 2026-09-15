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

from mtgcoach.api.boards import all_boards, boards
from mtgcoach.api.context import Seated, session, snapshot
from mtgcoach.api.eventfields import BadEventError
from mtgcoach.api.eventspec import parse
from mtgcoach.api.guard import check
from mtgcoach.api.seats import MAX_SEAT, plays_in
from mtgcoach.api.sessions import UnknownSessionError
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import AdvanceStep

#: What a socket is closed with, in the 4000-4999 range the application owns.
#: The two refusals a watching client can act on: the game is not there, or it
#: is not this seat's.
NO_SUCH_GAME = 4004
NOT_YOUR_GAME = 4003

if TYPE_CHECKING:
    from fastapi import FastAPI

    from mtgcoach.api.context import Server
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json
    from mtgcoach.core.events import Event


def sent_by(event: Event, seat: str) -> None:
    """Refuse an event that names a player other than the one that sent it.

    ``AdvanceStep`` is the exception and names nobody, because ending a step is
    not a player's action: it happens when every player has passed in
    succession on an empty stack (CR 500.2), and ``core.turn.advance`` refuses
    it until both halves of that hold. So either device may send it, and
    neither can use it to get ahead of the other -- the passes it needs first
    are seated events, checked here like any other.

    Raises:
        HTTPException: 403 if the event names another seat. Not 400: the
            request is well formed and the engine would accept it. What is
            wrong is who sent it, and a client cannot fix that by rewriting the
            body.
    """
    if isinstance(event, AdvanceStep):
        return
    named = str(event.player)
    if named != seat:
        # Truncated, for the reason `thinking._asking` truncates the same
        # field: this reaches a client and the CORS policy is `*`, so a
        # megabyte of posted nonsense must not come back out.
        msg = f"your token is {seat!r}; it cannot send an event for {named[:MAX_SEAT]!r}"
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
        # applied it twice, and every later read failed the same way.
        board = boards(server, advanced)
        mine = all_boards(server, session_id, board, seat)
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
        board = boards(server, undone)
        mine = all_boards(server, session_id, board, seat)
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
        game = await _watchable(server, websocket, session_id, seat)
        if game is None:
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


async def _watchable(
    server: Server, websocket: WebSocket, session_id: str, seat: str
) -> Session | None:
    """The game this socket may follow, or None having closed it with a reason.

    Two refusals, and a socket has no status codes to make them with -- so each
    is a close code in the 4000-4999 range the application owns, plus a
    sentence. Letting ``snapshot``'s 403 stand instead would raise an
    ``HTTPException`` inside a socket handler, which is not a status code but
    an unhandled error.
    """
    try:
        game = server.store.get(session_id)
    except UnknownSessionError:
        await websocket.close(code=NO_SUCH_GAME, reason="no such game")
        return None
    if not plays_in(game.state, seat):
        # A game adopted from somebody else's journal can be between seats this
        # server has no token for.
        await websocket.close(code=NOT_YOUR_GAME, reason="this game is not yours")
        return None
    return game
