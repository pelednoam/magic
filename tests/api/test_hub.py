"""Who is watching, and what happens when one of them goes away."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from starlette.websockets import WebSocketDisconnect

from mtgcoach.api.hub import Hub

if TYPE_CHECKING:
    from collections.abc import Coroutine


def run(work: Coroutine[object, object, int]) -> int:
    """Drive one coroutine to completion.

    ``asyncio.run`` rather than a pytest plugin: the hub has no framework in it
    and its tests should not need one either.
    """
    return asyncio.run(work)


if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.api.views import Json


class DisconnectedError(Exception):
    """What Starlette raises for a dead socket.

    A bare ``Exception``, like uvicorn's ``ConnectionClosed`` -- neither is an
    ``OSError`` and neither is a ``RuntimeError``. The first version of the hub
    caught those two and so caught neither of the ones that happen, and this
    file's fake raised ``OSError``: the one case that *was* caught. The test
    passed and the code was broken.
    """


@dataclass(slots=True)
class Client:
    """A watcher that remembers what it was told, and can be made to fail."""

    heard: list[Mapping[str, Json]] = field(default_factory=list["Mapping[str, Json]"])
    broken: bool = False

    async def send_json(self, data: Mapping[str, Json]) -> None:
        """Deliver, or fail the way a closed socket fails."""
        if self.broken:
            msg = "connection closed"
            raise OSError(msg)
        self.heard.append(data)


def test_a_watcher_is_told() -> None:
    hub, client = Hub(), Client()
    hub.join("g", client)
    assert run(hub.broadcast("g", {"turn": 1})) == 1
    assert client.heard == [{"turn": 1}]


def test_everyone_watching_is_told() -> None:
    """The phone and the laptop are two views of one game."""
    hub = Hub()
    phone, laptop = Client(), Client()
    hub.join("g", phone)
    hub.join("g", laptop)
    assert run(hub.broadcast("g", {"turn": 1})) == 2


def test_only_the_watchers_of_that_game() -> None:
    hub = Hub()
    ours, theirs = Client(), Client()
    hub.join("ours", ours)
    hub.join("theirs", theirs)
    run(hub.broadcast("ours", {"turn": 1}))
    assert theirs.heard == []


def test_a_dead_connection_is_dropped_and_the_rest_still_hear() -> None:
    """A phone going to sleep must not stop the laptop being told."""
    hub = Hub()
    asleep, awake = Client(broken=True), Client()
    hub.join("g", asleep)
    hub.join("g", awake)
    assert run(hub.broadcast("g", {"turn": 1})) == 1
    assert awake.heard == [{"turn": 1}]
    assert hub.watchers("g") == (awake,)


def test_broadcasting_to_a_game_nobody_watches() -> None:
    assert run(Hub().broadcast("g", {"turn": 1})) == 0


def test_leaving_removes_the_room_when_it_empties() -> None:
    hub, client = Hub(), Client()
    hub.join("g", client)
    hub.leave("g", client)
    assert hub.rooms == {}


def test_leaving_twice_is_silent() -> None:
    """It is called from a `finally`; a raise there would hide the real error."""
    hub, client = Hub(), Client()
    hub.join("g", client)
    hub.leave("g", client)
    hub.leave("g", client)
    hub.leave("never", client)


@dataclass(slots=True)
class Dropped:
    """A watcher whose socket died the way Starlette reports it."""

    async def send_json(self, data: Mapping[str, Json]) -> None:
        """Fail the way a real disconnection fails."""
        assert data is not None
        raise DisconnectedError


def test_a_disconnection_is_caught_whatever_type_it_is() -> None:
    """The exception types are not ours to enumerate.

    Starlette raises `WebSocketDisconnect`, uvicorn's implementation raises
    `websockets.exceptions.ConnectionClosed`, and a future version may raise
    something else again. All that matters is that the send failed.
    """
    hub = Hub()
    gone, here = Dropped(), Client()
    hub.join("g", gone)
    hub.join("g", here)
    assert run(hub.broadcast("g", {"turn": 1})) == 1
    assert hub.watchers("g") == (here,)


def test_the_real_disconnect_type_is_not_one_we_could_have_named() -> None:
    """Pinned, because it is why the original catch was wrong."""
    assert not issubclass(WebSocketDisconnect, OSError)
    assert not issubclass(WebSocketDisconnect, RuntimeError)
