"""Walking a played game, one decision at a time.

Three routes, and the third is the one that makes it teaching rather than a
log viewer: stepping *into* a moment adopts its board as a real game, so every
route that already exists works on it. The child asks "why?" about turn seven
and the rules question route answers about turn seven's board; the coach route
gives its view of the same position; and playing on from there shows what the
other line would have done.

None of it re-asks the model. The board comes from the recorded events and the
advice from the journal, so what is shown is what happened -- which matters
more here than anywhere else in this project, because somebody is learning the
rules from it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from mtgcoach.api import views
from mtgcoach.api.context import snapshot
from mtgcoach.api.replays import UnknownReplayError, games_in, journals

if TYPE_CHECKING:
    from fastapi import FastAPI

    from mtgcoach.api.context import Server
    from mtgcoach.api.replays import Moment, Replay
    from mtgcoach.api.views import Json
    from mtgcoach.core.ids import OracleId


def routes(app: FastAPI, server: Server) -> None:
    """Attach the three replay routes."""

    @app.get("/replays", response_model=None)
    def list_replays() -> dict[str, Json]:
        """Every journal this server can show, newest first."""
        if server.data_root is None:
            return {"replays": []}
        return {"replays": list(journals(server.data_root))}

    @app.get("/replays/{name}", response_model=None)
    def read_replay(name: str) -> dict[str, Json]:
        """Every game in one journal, with every moment of each."""
        return {"games": [walked(game) for game in _found(server, name)]}

    @app.post("/replays/{name}/{seed}/at/{index}", response_model=None)
    def step_into(name: str, seed: int, index: int) -> dict[str, Json]:
        """Adopt one moment as a game, so it can be asked about.

        Returns the same shape as starting a game, because it *is* one from
        here on -- which is what lets the question box, the coach and the
        board all work on a position out of somebody else's game without a
        single route knowing it came from a replay.
        """
        stepped = _moment(_found(server, name), seed, index)
        started = server.store.adopt(stepped.state)
        return {"session_id": started.session_id, **snapshot(server, started)}


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


def _moment(games: tuple[Replay, ...], seed: int, index: int) -> Moment:
    """One moment of one game.

    Raises:
        HTTPException: 404 when the game or the moment is not there.
    """
    game = next((one for one in games if one.seed == seed), None)
    if game is None or not 0 <= index < len(game.moments):
        msg = f"no moment {index} in game {seed}"
        raise HTTPException(HTTP_404_NOT_FOUND, msg)
    return game.moments[index]


def walked(game: Replay) -> dict[str, Json]:
    """One game, as something a screen can page through."""
    return {
        "seed": game.seed,
        "decks": list(game.decks),
        "moments": [moment(one) for one in game.moments],
    }


def moment(one: Moment) -> dict[str, Json]:
    """One moment: where in the game, the board, and what was said about it.

    The board goes out as ``views.state`` -- the same shape a live game sends
    -- so the app renders a replayed position with the components it already
    has, and a position looks the same whether it is happening now or happened
    last night.
    """
    return {
        "turn": one.turn,
        "step": str(one.step),
        "player": one.player,
        "state": views.state(one.state, _naming),
        "said": views.explanation(one.said) if one.said is not None else None,
        "trusted": one.trusted,
        "problems": list(one.problems),
        "error": one.error,
    }


def _naming(oracle_id: OracleId) -> str:
    """A card's name for the board view.

    A replay carries no catalogue: a journal is a game, not a card database,
    and the set it was played with may not be the set this server has loaded.
    So the oracle id is shown as the name -- which for this project *is* the
    name, because that is what the importer uses as the identifier.
    """
    return str(oracle_id)
