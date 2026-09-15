"""How many boards one change makes, and when each of them is built.

Split from ``acting`` at the line limit, and the seam is a real one: that
module is the routes and the refusal, this is the arithmetic of a change that
has to reach two devices with two different payloads.

There is one rule here and it is about *ordering*. A board is built before the
event is committed, so a payload that will not build fails while the event can
still be refused -- rather than after the store has it, when the same error is
a 500 for a stored event and a client retry applies it twice.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api.context import snapshot

if TYPE_CHECKING:
    from collections.abc import Callable

    from mtgcoach.api.context import Server
    from mtgcoach.api.sessions import Session
    from mtgcoach.api.views import Json


def all_boards(
    server: Server, session_id: str, board: Callable[[str], dict[str, Json]], seat: str
) -> dict[str, Json]:
    """Every payload this change will send, built while nothing is committed.

    Returns the sender's own, which is what the route answers with.

    The hub builds a watcher's board *outside* its ``try`` on purpose -- a
    payload that will not build is a bug, not a dropped socket -- so an error
    there escapes the broadcast and the route. After ``record`` that is a 500
    for an event the store already has, the client retries, and the event is
    applied twice: the failure ``hub``'s own docstring says must not happen.
    Building every seat's board first moves it to where the event can still be
    refused. ``board`` remembers each one, so the broadcast pays nothing.
    """
    mine = board(seat)
    for watching in server.hub.watchers(session_id):
        board(watching.seat)
    return mine


def boards(server: Server, game: Session) -> Callable[[str], dict[str, Json]]:
    """The board for a seat, worked out once per seat and then remembered.

    One change produces up to three payloads -- the answer to the device that
    sent it and one per watching seat -- and they differ only in which hand
    they carry. Building each from scratch would advise a player twice for
    every tap, and advising is the expensive half of a snapshot: it searches
    the attacks.

    Remembered rather than built for every seat up front, which was the other
    way to make the ordering safe. A seat nobody is watching from costs a whole
    combat search under that arrangement, on every event of every game --
    ``all_boards`` builds exactly the payloads that will be sent, which is both
    cheaper and the same guarantee.
    """
    made: dict[str, dict[str, Json]] = {}

    def board(seat: str) -> dict[str, Json]:
        if seat not in made:
            made[seat] = snapshot(server, game, seat)
        return made[seat]

    return board
