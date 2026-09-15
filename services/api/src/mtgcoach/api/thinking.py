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

Both are also rationed -- see ``rationing``, which says why that is about a
stuck finger rather than about an attacker.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import (
    HTTP_400_BAD_REQUEST,
    HTTP_403_FORBIDDEN,
    HTTP_503_SERVICE_UNAVAILABLE,
)

from mtgcoach.api.asking import answered
from mtgcoach.api.coaching import coached
from mtgcoach.api.context import Seated, position, session
from mtgcoach.api.seats import seated_in
from mtgcoach.coach.advice import ExplainerError

if TYPE_CHECKING:
    from collections.abc import Generator

    from fastapi import FastAPI

    from mtgcoach.api.context import Server
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json
    from mtgcoach.core.ids import PlayerId


#: The longest question this will carry. A rules question is a sentence; past
#: this it is either a mistake or somebody filling the prompt with their own
#: text, and both are answered better by saying so than by forwarding it.
MAX_QUESTION = 500

#: The longest seat name worth echoing back. The real ones are "you" and
#: "them"; anything longer is not a seat and does not need quoting in full.
MAX_SEAT = 40


@contextmanager
def _rationed(server: Server) -> Generator[None]:
    """Take one of this server's slots, or refuse.

    Acquired without waiting: a request that queued would just sit on a
    threadpool worker, which is the resource being rationed.

    Raises:
        HTTPException: 503 when there is nothing to take. Honest and
            actionable: the engine's own advice is already on screen, and
            trying again in a moment is exactly the right thing to do.
    """
    refused = server.rations.take()
    if refused:
        raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, refused)
    try:
        yield
    finally:
        server.rations.release()


def routes(app: FastAPI, server: Server) -> None:
    """Attach both of them."""

    @app.post("/games/{session_id}/coach", response_model=None)
    def coach(session_id: str, body: dict[str, str], seat: Seated) -> dict[str, Json]:
        """Ask Claude what to do about this device's own turn."""
        game, player = _asking(server, session_id, body, seat)
        try:
            # The engine work is inside the limiter too. It is milliseconds
            # next to the subprocess, but it is not free, and a limit that only
            # covers the cheap half of a request is not a limit.
            with _rationed(server):
                return coached(server.explainer, position(server, game, player))
        except ExplainerError as unavailable:
            # Not a server fault and not fatal: the deterministic panel is
            # already on screen and already right. 503 says "try again", which
            # is the truth about a flaky subprocess.
            raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, str(unavailable)) from unavailable

    @app.post("/games/{session_id}/ask", response_model=None)
    def ask(session_id: str, body: dict[str, str], seat: Seated) -> dict[str, Json]:
        """Answer a rules question, from rules retrieved for it."""
        # The game first, so that a question about a game that is not there is
        # a 404 rather than whichever of these checks happens to fire.
        game, player = _asking(server, session_id, body, seat)
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
            with _rationed(server):
                asked = position(server, game, player, board=True)
                return answered(server.asker, server.rules, question, asked)
        except ExplainerError as unavailable:
            raise HTTPException(HTTP_503_SERVICE_UNAVAILABLE, str(unavailable)) from unavailable


def _asking(
    server: Server, session_id: str, body: dict[str, str], seat: str
) -> tuple[Session, PlayerId]:
    """The game, and the player it is being asked about.

    Always the seat the token names. Both of these routes put a hand in a
    prompt -- the coach's briefing names every card in it, and the rules
    answerer quotes the printed text of each -- so a request that could ask
    about the *other* seat was a way to read their hand out of a model's
    answer, one token and one ``{"player": "them"}`` away.

    The body may still name a player, and it has to agree. A client that sends
    the wrong one is refused rather than quietly answered about itself: the
    answer would be right and its own belief about who it is would stay wrong,
    which is the kind of disagreement that surfaces later as a mystery.

    Raises:
        HTTPException: 404 for a game that is not there, and 403 both for a
            body naming another seat and for a seat that is not a player in
            this game -- which a game adopted from somebody else's journal
            really can be. See ``context.seated_in``.
    """
    game = session(server, session_id)
    claimed = body.get("player", seat)[:MAX_SEAT]
    if claimed != seat:
        # Truncated above, so the message cannot be a megabyte of whatever was
        # posted -- this reaches a client, and the CORS policy is `*`.
        msg = f"your token is {seat!r}; it cannot ask as {claimed!r}"
        raise HTTPException(HTTP_403_FORBIDDEN, msg)
    return game, seated_in(game, seat)
