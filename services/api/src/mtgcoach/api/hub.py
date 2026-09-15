"""Who is watching which game, from which seat, and telling them when it changes.

Deliberately a plain object with no framework in it. A WebSocket here is
anything that can be sent a JSON object, so the fan-out logic -- which is the
part with a bug in it, always -- is testable without a server, a client, or an
event loop that has to be started and stopped.

A send that fails *or stalls* drops that watcher and carries on. One phone going to sleep
mid-turn must not stop the laptop being told what happened, and the alternative
-- an exception escaping the broadcast -- would fail the *event* rather than the
connection: the route returns 500 for a move the server already committed, the
client retries it, and it is applied twice.

"Fails" means *any* exception. The first version named two types and caught
neither of the ones that actually occur, and its test passed because the fake
watcher raised one of the two it did catch.

**Each watcher gets its own payload.** A board is not the same for both seats
-- one carries your hand and not theirs -- so a broadcast takes a function from
seat to message rather than a message. It is called once per *seat* watching,
not once per watcher: two devices on one seat are two sockets and one payload.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from mtgcoach.api.views import Json


#: How long one watcher gets to accept a message. A game update is a few
#: kilobytes to a device in the same room; anything slower than this is a
#: connection that has gone away without saying so.
SEND_TIMEOUT = 5.0


class Watcher(Protocol):
    """Anything that can be told a game has changed."""

    async def send_json(self, data: Mapping[str, Json]) -> None:
        """Deliver one message, or raise if the connection is gone."""
        ...


#: How a broadcaster asks for the payload one seat should be sent. A function
#: rather than a message, because the two seats are sent different boards; see
#: ``acting._boards``, which builds each at most once.
type Boards = Callable[[str], Mapping[str, "Json"]]


@dataclass(frozen=True, slots=True)
class Seated:
    """One watcher, and the seat whose board it is sent.

    The seat comes from the token the socket presented, so a device cannot
    subscribe to the other player's view of the game by asking for it.
    """

    watcher: Watcher
    seat: str


@dataclass(slots=True)
class Hub:
    """Every client watching every game, and from which seat."""

    rooms: dict[str, list[Seated]] = field(default_factory=dict[str, list["Seated"]])

    def join(self, session_id: str, watcher: Watcher, seat: str) -> None:
        """Start sending this watcher a game's changes, as this seat sees them."""
        self.rooms.setdefault(session_id, []).append(Seated(watcher, seat))

    def leave(self, session_id: str, watcher: Watcher) -> None:
        """Stop sending them a game's changes.

        Silent if they were not watching. A client that disconnects twice is
        ordinary, and this is called from a ``finally``, where a raise would
        replace the real error with a bookkeeping one.
        """
        watchers = self.rooms.get(session_id)
        if watchers is None:
            return
        # By identity, not equality: a watcher is a live connection and two of
        # them are never the same one, however they compare. `remove` used the
        # `==` a test double is free to define.
        kept = [one for one in watchers if one.watcher is not watcher]
        if len(kept) == len(watchers):
            return
        if not kept:
            del self.rooms[session_id]
            return
        self.rooms[session_id] = kept

    def watchers(self, session_id: str) -> tuple[Seated, ...]:
        """Who is watching this game, and from where."""
        return tuple(self.rooms.get(session_id, ()))

    async def broadcast(self, session_id: str, boards: Boards) -> int:
        """Tell everyone watching, and return how many heard it.

        Dropped connections are removed as they are found. The count is what
        makes this testable from the outside: "two were watching, two were
        told" is an assertion; "no exception was raised" is not.
        """
        heard = 0
        for seated in self.watchers(session_id):
            # Built outside the `try`, deliberately. Everything caught below
            # means "that connection is gone"; a payload that will not build
            # means this server has a bug, and treating it as a dropped socket
            # would quietly unsubscribe a device from its own game. `boards`
            # has already built this seat's board for the reply, so in practice
            # nothing here can fail.
            message = boards(seated.seat)
            try:
                # Bounded, because a socket that is open but not being drained
                # blocks forever: it would hold up every later watcher *and*
                # the HTTP request that caused the broadcast, so one phone in a
                # tunnel freezes the game for the person holding the laptop.
                async with asyncio.timeout(SEND_TIMEOUT):
                    await seated.watcher.send_json(message)
            except Exception:  # noqa: BLE001 - see below
                # Every failure to send means that connection is gone, and the
                # exception types are not ours to enumerate: Starlette raises
                # `WebSocketDisconnect`, uvicorn's implementation raises
                # `websockets.exceptions.ConnectionClosed`, and both are bare
                # `Exception` subclasses. Catching (OSError, RuntimeError)
                # caught neither, so one sleeping phone let the exception
                # escape the broadcast, escape the route, and return 500 for an
                # event the server had already committed -- exactly what this
                # module's docstring says must not happen.
                self.leave(session_id, seated.watcher)
            else:
                heard += 1
        return heard
