"""Who is watching, and what happens when one of them goes away."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

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
