"""Which seat is talking, and whether that seat plays in this game.

Split from ``context`` at the line limit, and the seam is a real one: that
module is what a server *is* and what it *sends*, and these are the two
questions every route asks before it does either. Both are about identity and
neither is about a game.

``gatekeeper`` decides who is asking, from the token. ``seated`` lifts that
answer out of the connection, and ``seated_in`` is the refusal for the one case
where an authenticated seat still may not be served.

The route-facing alias -- ``context.Seated``, built out of ``seated`` -- stays
in ``context`` deliberately. Every route module already imports that at
runtime, and a separate import of the alias would need a ``noqa`` in each of
them: FastAPI resolves the signature at import time, so the name cannot be
deferred, and there is nothing to learn from four identical exemptions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.requests import HTTPConnection  # noqa: TC002 - see `seated`
from starlette.status import HTTP_403_FORBIDDEN

from mtgcoach.api.gatekeeper import seat_of
from mtgcoach.core.ids import PlayerId

if TYPE_CHECKING:
    from mtgcoach.api.sessions import Session


def seated(connection: HTTPConnection) -> str:
    """Which seat this connection authenticated as.

    ``HTTPConnection`` rather than ``Request``, because it is the base of both
    that and ``WebSocket`` and FastAPI fills it in for either -- and the socket
    is the connection that most needs a seat, being the one that streams a
    whole board every time anything happens.

    Its import cannot move into a type-checking block, which is why there is a
    ``noqa`` on it. FastAPI resolves this signature at import time to decide
    what to pass; under ``from __future__ import annotations`` the name has to
    be there when it looks, and a deferred import makes this an undeclared body
    parameter instead -- a 422 on every request, with nothing saying why.
    """
    return seat_of(connection.scope)


def seated_in(game: Session, seat: str) -> PlayerId:
    """This seat, as a player of this game.

    Every game *this* server deals has both of ``seating.SEATS`` in it, so in
    ordinary play this cannot fail. A game adopted from a journal has whatever
    seats that journal used, and what happens then must not be a 500 or, worse,
    advice about a player who is not there.

    One function, called by everything that pairs a seat with a game -- the
    snapshot and both slow routes. Two checks of the same condition is one of
    them being wrong later.

    Raises:
        HTTPException: 403 if this seat is not a player in this game.
    """
    player = PlayerId(seat)
    if player not in game.state.players:
        seated_here = ", ".join(sorted(str(one) for one in game.state.players))
        raise HTTPException(HTTP_403_FORBIDDEN, f"this game is between {seated_here}, not you")
    return player
