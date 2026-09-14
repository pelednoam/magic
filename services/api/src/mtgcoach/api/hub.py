"""Who is watching which game, and telling them when it changes.

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
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Mapping

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


@dataclass(slots=True)
class Hub:
    """Every client watching every game."""

    rooms: dict[str, list[Watcher]] = field(default_factory=dict[str, list["Watcher"]])

    def join(self, session_id: str, watcher: Watcher) -> None:
        """Start sending this watcher a game's changes."""
        self.rooms.setdefault(session_id, []).append(watcher)

    def leave(self, session_id: str, watcher: Watcher) -> None:
        """Stop sending them a game's changes.

        Silent if they were not watching. A client that disconnects twice is
        ordinary, and this is called from a ``finally``, where a raise would
        replace the real error with a bookkeeping one.
        """
        watchers = self.rooms.get(session_id)
        if watchers is None or watcher not in watchers:
            return
        watchers.remove(watcher)
        if not watchers:
            del self.rooms[session_id]

    def watchers(self, session_id: str) -> tuple[Watcher, ...]:
        """Who is watching this game."""
        return tuple(self.rooms.get(session_id, ()))

    async def broadcast(self, session_id: str, message: Mapping[str, Json]) -> int:
        """Tell everyone watching, and return how many heard it.

        Dropped connections are removed as they are found. The count is what
        makes this testable from the outside: "two were watching, two were
        told" is an assertion; "no exception was raised" is not.
        """
        heard = 0
        for watcher in self.watchers(session_id):
            try:
                # Bounded, because a socket that is open but not being drained
                # blocks forever: it would hold up every later watcher *and*
                # the HTTP request that caused the broadcast, so one phone in a
                # tunnel freezes the game for the person holding the laptop.
                async with asyncio.timeout(SEND_TIMEOUT):
                    await watcher.send_json(message)
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
                self.leave(session_id, watcher)
            else:
                heard += 1
        return heard
