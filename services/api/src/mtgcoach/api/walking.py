"""Walking a played game, one decision at a time.

Four routes, and the last is the one that makes it teaching rather than a log
viewer: stepping *into* a moment adopts its board as a real game, so every
route that already exists works on it. The child asks "why?" about turn seven
and the rules question route answers about turn seven's board; the coach route
gives its view of the same position; and playing on from there shows what the
other line would have done.

None of it re-asks the model. The board comes from the recorded events and the
advice from the journal, so what is shown is what happened -- which matters
more here than anywhere else in this project, because somebody is learning the
rules from it.

A game is addressed by its **position** in the journal. Two runs into the same
journal repeat a seed, and a seed is then not an address: it would put one
game's moments under another game's name. The seed still travels, because it is
what re-runs the game, and it is a label rather than a key.

Four routes and the finding of a game; ``walked`` is how one is rendered. Split
at the line limit, and the seam is a real one -- these are the refusals (404s, a
403 for a seat that is not in the game) and that is the JSON.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from mtgcoach.api.context import Seated, snapshot
from mtgcoach.api.replays import UnknownReplayError, games_in, journals
from mtgcoach.api.seats import seated_in
from mtgcoach.api.walked import listed, walked

if TYPE_CHECKING:
    from fastapi import FastAPI

    from mtgcoach.api.context import Server
    from mtgcoach.api.decisions import Moment
    from mtgcoach.api.replays import Replay
    from mtgcoach.api.views import Json


def routes(app: FastAPI, server: Server) -> None:
    """Attach the four replay routes."""

    @app.get("/replays", response_model=None)
    def list_replays() -> dict[str, Json]:
        """Every journal this server can show, newest first."""
        if server.data_root is None:
            return {"replays": []}
        return {"replays": list(journals(server.data_root))}

    @app.get("/replays/{name}", response_model=None)
    def read_replay(name: str) -> dict[str, Json]:
        """What is in one journal: a line per game, and no boards.

        Deliberately without the moments. A twelve-game coached season is
        several megabytes of board once every position is serialised, and this
        route answers "which game?" -- a question that needs the decks, the
        length and nothing else. The chosen game is then one more request.
        """
        return {"games": [listed(server, game) for game in _found(server, name)]}

    @app.get("/replays/{name}/{game}", response_model=None)
    def read_game(name: str, game: int) -> dict[str, Json]:
        """One game, with every moment of it.

        The whole game in one request, so stepping is instant and the back
        button is exactly as fast as the forward one -- which matters on a
        screen whose entire purpose is going back over something.
        """
        return walked(server, _game(_found(server, name), game))

    @app.post("/replays/{name}/{game}/at/{index}", response_model=None)
    def step_into(name: str, game: int, index: int, seat: Seated) -> dict[str, Json]:
        """Adopt one moment as a game, so it can be asked about.

        Returns the same shape as starting a game, because it *is* one from
        here on -- which is what lets the question box, the coach and the
        board all work on a position out of somebody else's game without a
        single route knowing it came from a replay.

        And because it is a game from here on, it is played from a seat: this
        device is shown its own hand, though the moment it stepped in from
        showed both. Reading a finished game is not playing one, and the
        instant somebody can *act* on a position the rules about who may see
        what apply again.
        """
        stepped = _moment(_game(_found(server, name), game), index)
        # Before adopting, not after. A moment out of somebody else's journal
        # can be between seats this server has no token for, and adopting it
        # first left a game in the store that nobody could ever read.
        seated_in(stepped.state, seat)
        started = server.store.adopt(stepped.state)
        return {"session_id": started.session_id, **snapshot(server, started, seat)}


def _found(server: Server, name: str) -> tuple[Replay, ...]:
    """The games in a journal.

    Raises:
        HTTPException: 404 when there is no such journal, or nothing in it
            that can be rebuilt.
    """
    if server.data_root is None:
        raise HTTPException(HTTP_404_NOT_FOUND, "this server has no replays")
    try:
        return games_in(server.data_root, name)
    except UnknownReplayError as missing:
        raise HTTPException(HTTP_404_NOT_FOUND, str(missing)) from missing


def _game(games: tuple[Replay, ...], index: int) -> Replay:
    """One game of a journal, by its position in the file.

    Found by its own ``index``, not by where it sits in this tuple. A game that
    will not rebuild is left out of the tuple and keeps its place in the file,
    so the two stop agreeing the moment a journal holds one damaged game -- and
    since the list route hands out file positions, ``at/2`` would then open a
    different game than the one the list said was there.

    Raises:
        HTTPException: 404 when there is no game there.
    """
    found = next((game for game in games if game.index == index), None)
    if found is None:
        listed = ", ".join(str(game.index) for game in games) or "none"
        msg = f"no game {index} in this journal; it has {listed}"
        raise HTTPException(HTTP_404_NOT_FOUND, msg)
    return found


def _moment(game: Replay, index: int) -> Moment:
    """One moment of one game.

    Raises:
        HTTPException: 404 when the moment is not there.
    """
    if not 0 <= index < len(game.moments):
        msg = f"no moment {index} in game {game.index}"
        raise HTTPException(HTTP_404_NOT_FOUND, msg)
    return game.moments[index]
