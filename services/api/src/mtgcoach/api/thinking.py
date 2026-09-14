"""The two routes that ask Claude, which are the two that take a minute.

Together because they share everything that makes them unusual: they are slow,
they are optional, they cost quota rather than microseconds, and each one has a
checker standing between the model and the client. Everything else this server
does is instant and certain; these two are neither, and keeping them in one
file is a way of saying so.

Both are deliberately **not** ``async def``. Asking is a subprocess that can
take a minute, and an async route would hold the event loop for all of it --
freezing every other player's socket. FastAPI runs a plain ``def`` in a
threadpool, which is exactly the behaviour wanted here.

Both are also rationed. There is no auth on this server (§4: one LAN, one
table), so anything unauthenticated that starts a minute-long Node process is a
way to bring the laptop down by holding down a button. The semaphore below is
not a security boundary -- nothing here is -- but it turns "unbounded processes"
into "a queue", which is the difference between a slow tracker and a dead one.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST, HTTP_503_SERVICE_UNAVAILABLE

from mtgcoach.api.asking import answered
from mtgcoach.api.coaching import coached
from mtgcoach.api.context import position, session
from mtgcoach.coach.advice import ExplainerError
from mtgcoach.core.ids import PlayerId

if TYPE_CHECKING:
    from collections.abc import Generator

    from fastapi import FastAPI

    from mtgcoach.api.context import Server
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json


#: The longest question this will carry. A rules question is a sentence; past
#: this it is either a mistake or somebody filling the prompt with their own
#: text, and both are answered better by saying so than by forwarding it.
MAX_QUESTION = 500


@contextmanager
def _one_at_a_time(server: Server) -> Generator[None]:
    """Take one of this server's slots, or refuse.

    Acquired without waiting: a request that queued would just sit on a
    threadpool worker, which is the resource being rationed.

    Raises:
        HTTPException: 503 when every slot is busy. Honest and actionable: the
            engine's own advice is already on screen, and trying again in a
            moment is exactly the right thing to do.
    """
    if not server.in_flight.acquire(blocking=False):
        raise HTTPException(
            HTTP_503_SERVICE_UNAVAILABLE,
            "the coach is busy with another question; try again in a moment",
        )
    try:
        yield
    finally:
        server.in_flight.release()


def routes(app: FastAPI, server: Server) -> None:
    """Attach both of them."""

    @app.post("/games/{session_id}/coach", response_model=None)
    def coach(session_id: str, body: dict[str, str]) -> dict[str, Json]:
        """Ask Claude what to do about this player's turn."""
        game, player = _seat(server, session_id, body)
        try:
            # The engine work is inside the limiter too. It is milliseconds
            # next to the subprocess, but it is not free, and a limit that only
            # covers the cheap half of a request is not a limit.
            with _one_at_a_time(server):
                return coached(server.explainer, position(server, game, player))
        except ExplainerError as unavailable:
            # Not a server fault and not fatal: the deterministic panel is
            # already on screen and already right. 503 says "try again", which
            # is the truth about a flaky subprocess.
            raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, str(unavailable)) from unavailable

    @app.post("/games/{session_id}/ask", response_model=None)
    def ask(session_id: str, body: dict[str, str]) -> dict[str, Json]:
        """Answer a rules question, from rules retrieved for it."""
        # The game first, so that a question about a game that is not there is
        # a 404 rather than whichever of these checks happens to fire.
        game, player = _seat(server, session_id, body)
        question = body.get("question", "").strip()
        if not question:
            raise HTTPException(HTTP_400_BAD_REQUEST, "ask a question")
        if len(question) > MAX_QUESTION:
            raise HTTPException(
                HTTP_400_BAD_REQUEST,
                f"that question is {len(question)} characters; keep it under {MAX_QUESTION}",
            )
        if server.rules is None:
            raise HTTPException(
                HTTP_503_SERVICE_UNAVAILABLE,
                "the Comprehensive Rules are not installed on this server",
            )
        try:
            with _one_at_a_time(server):
                asked = position(server, game, player, board=True)
                return answered(server.asker, server.rules, question, asked)
        except ExplainerError as unavailable:
            raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, str(unavailable)) from unavailable


def _seat(server: Server, session_id: str, body: dict[str, str]) -> tuple[Session, PlayerId]:
    """The game and the player being asked about.

    Raises:
        HTTPException: 404 for a game that is not there, 400 for a seat that is
            not in it. The default is "you", which is what a phone with one
            player at the table sends.
    """
    game = session(server, session_id)
    player = PlayerId(body.get("player", "you"))
    if player not in game.state.players:
        raise HTTPException(HTTP_400_BAD_REQUEST, f"no player {player}")
    return game, player
