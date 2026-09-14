"""Everything the routes share: what a server is, and what it sends.

Separate from ``app`` so that the routes there read as a list of routes. The
snapshot in particular is the single most important thing this service produces
-- it is what every client renders and what the wire contract test pins -- and
it deserves to be somewhere you can find it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_404_NOT_FOUND

from mtgcoach.api import views
from mtgcoach.api.sessions import SessionStore, UnknownSessionError
from mtgcoach.coach.report import advise

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.api.cards import Catalogue
    from mtgcoach.api.hub import Hub
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json
    from mtgcoach.coach.advice import Explainer


@dataclass(slots=True)
class Server:
    """Everything the routes need, in one place they can be given in a test."""

    catalogue: Catalogue
    store: SessionStore
    hub: Hub
    decks: Mapping[str, tuple[str, ...]]
    explainer: Explainer


def session(server: Server, session_id: str) -> Session:
    """The game, or a 404."""
    try:
        return server.store.get(session_id)
    except UnknownSessionError as missing:
        raise HTTPException(HTTP_404_NOT_FOUND, "no such game") from missing


def snapshot(server: Server, game: Session) -> dict[str, Json]:
    """The board, plus what each player can do about it.

    Advice for *both* players in one payload: the tracker is one screen at a
    kitchen table, and the person defending needs the block advice as much as
    the attacker needs the attack advice.
    """
    return {
        # How many times this game has changed. The client uses it to ignore a
        # stale reply: an HTTP response and a broadcast race, and without an
        # ordering the older of the two could permanently roll the board back.
        # It counts *changes*, not events -- undo is a change that removes one,
        # so counting events made this go backwards and the client threw away
        # every undo.
        "version": game.revision,
        "state": views.state(game.state, server.catalogue.name),
        "advice": {
            str(player): views.report(advise(game.state, player, server.catalogue))
            for player in game.state.players
        },
    }
