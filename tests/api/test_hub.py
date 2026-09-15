"""Who is watching, from which seat, and what happens when one goes away."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from unittest.mock import patch

from starlette.websockets import WebSocketDisconnect

from mtgcoach.api.hub import Hub, Seated

if TYPE_CHECKING:
    from collections.abc import Coroutine, Mapping

    from mtgcoach.api.views import Json

#: The seats two watchers sit in. The hub does not care what they are called;
#: it cares that a payload built for one is not sent to the other.
MINE, THEIRS = "you", "them"


def boards(seat: str) -> Mapping[str, Json]:
    """A payload per seat, as `acting._boards` hands the hub one.

    It says which seat it was built for, which is what makes "each watcher got
    its own" an assertion rather than a hope.
    """
    return {"turn": 1, "seat": seat}


def run(work: Coroutine[object, object, int]) -> int:
    """Drive one coroutine to completion.

    ``asyncio.run`` rather than a pytest plugin: the hub has no framework in it
    and its tests should not need one either.
    """
    return asyncio.run(work)


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
    hub.join("g", client, MINE)
    assert run(hub.broadcast("g", boards)) == 1
    assert client.heard == [{"turn": 1, "seat": MINE}]


def test_everyone_watching_is_told() -> None:
    """The phone and the laptop are two views of one game."""
    hub = Hub()
    phone, laptop = Client(), Client()
    hub.join("g", phone, MINE)
    hub.join("g", laptop, THEIRS)
    assert run(hub.broadcast("g", boards)) == 2


def test_only_the_watchers_of_that_game() -> None:
    hub = Hub()
    ours, theirs = Client(), Client()
    hub.join("ours", ours, MINE)
    hub.join("theirs", theirs, MINE)
    run(hub.broadcast("ours", boards))
    assert theirs.heard == []


def test_a_dead_connection_is_dropped_and_the_rest_still_hear() -> None:
    """A phone going to sleep must not stop the laptop being told."""
    hub = Hub()
    asleep, awake = Client(broken=True), Client()
    hub.join("g", asleep, MINE)
    hub.join("g", awake, THEIRS)
    assert run(hub.broadcast("g", boards)) == 1
    assert awake.heard == [{"turn": 1, "seat": THEIRS}]
    assert hub.watchers("g") == (Seated(awake, THEIRS),)


def test_broadcasting_to_a_game_nobody_watches() -> None:
    assert run(Hub().broadcast("g", boards)) == 0


def test_leaving_removes_the_room_when_it_empties() -> None:
    hub, client = Hub(), Client()
    hub.join("g", client, MINE)
    hub.leave("g", client)
    assert hub.rooms == {}


def test_leaving_twice_is_silent() -> None:
    """It is called from a `finally`; a raise there would hide the real error."""
    hub, client = Hub(), Client()
    hub.join("g", client, MINE)
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
    hub.join("g", gone, MINE)
    hub.join("g", here, THEIRS)
    assert run(hub.broadcast("g", boards)) == 1
    assert hub.watchers("g") == (Seated(here, THEIRS),)


def test_the_real_disconnect_type_is_not_one_we_could_have_named() -> None:
    """Pinned, because it is why the original catch was wrong."""
    assert not issubclass(WebSocketDisconnect, OSError)
    assert not issubclass(WebSocketDisconnect, RuntimeError)


@dataclass(slots=True)
class Stalled:
    """A watcher whose socket is open and never drains."""

    async def send_json(self, data: Mapping[str, Json]) -> None:
        """Never finish."""
        assert data is not None
        await asyncio.sleep(3600)


def test_a_stalled_watcher_does_not_hold_up_the_game() -> None:
    """Awaited without a bound, one phone in a tunnel freezes the laptop.

    The send blocks forever, so every later watcher is starved *and* the HTTP
    request that caused the broadcast never returns.
    """
    hub = Hub()
    stuck, here = Stalled(), Client()
    hub.join("g", stuck, MINE)
    hub.join("g", here, THEIRS)
    with patch("mtgcoach.api.hub.SEND_TIMEOUT", 0.01):
        assert run(hub.broadcast("g", boards)) == 1
    assert here.heard == [{"turn": 1, "seat": THEIRS}]
    assert hub.watchers("g") == (Seated(here, THEIRS),)
