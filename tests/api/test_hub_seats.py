"""The hub, seat by seat: who gets which payload.

Split from `test_hub` at the length limit, and the seam is the subject. That
file is about a watcher going away -- a socket that fails, stalls or leaves.
This one is about the thing that made a broadcast take a *function* rather than
a message: two devices watching one game are sent two different boards, because
one carries your hand and the other carries theirs.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api.hub import Hub, Seated
from test_hub import MINE, THEIRS, Client, boards, run

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.api.views import Json


def test_each_seat_is_sent_its_own_board() -> None:
    """The whole reason a broadcast takes a function and not a message.

    One payload to both devices is how both hands reached both of them: the
    board that carries your hand is not the board that carries theirs, and
    there is no one message that is right for both.
    """
    hub = Hub()
    phone, laptop = Client(), Client()
    hub.join("g", phone, MINE)
    hub.join("g", laptop, THEIRS)
    run(hub.broadcast("g", boards))
    assert phone.heard == [{"turn": 1, "seat": MINE}]
    assert laptop.heard == [{"turn": 1, "seat": THEIRS}]


def test_two_watchers_on_one_seat_are_two_sockets_and_one_payload() -> None:
    """A seat may have the laptop and the phone both open on it.

    Both are told, and the board is built once -- which is the point of the
    memo in `acting._boards` and is checked here because this is the caller
    that decides how often it is asked.
    """
    hub = Hub()
    phone, laptop = Client(), Client()
    hub.join("g", phone, MINE)
    hub.join("g", laptop, MINE)
    asked: list[str] = []

    def counted(seat: str) -> Mapping[str, Json]:
        asked.append(seat)
        return {"turn": 1}

    assert run(hub.broadcast("g", counted)) == 2
    assert asked == [MINE, MINE], "the hub asks per watcher; `_boards` is what remembers"


def test_leaving_one_of_two_seats_keeps_the_other_watching() -> None:
    """The room is kept, and so is the watcher that did not leave."""
    hub = Hub()
    phone, laptop = Client(), Client()
    hub.join("g", phone, MINE)
    hub.join("g", laptop, THEIRS)
    hub.leave("g", phone)
    assert hub.watchers("g") == (Seated(laptop, THEIRS),)


def test_leaving_a_watcher_that_never_joined_leaves_the_room_alone() -> None:
    """Called from a `finally`, so it has to be silent about a stranger.

    And it must not empty the room: the socket that *is* watching is somebody's
    game, and dropping it here would stop their board updating with nothing
    raised anywhere.
    """
    hub = Hub()
    watching, stranger = Client(), Client()
    hub.join("g", watching, MINE)
    hub.leave("g", stranger)
    assert hub.watchers("g") == (Seated(watching, MINE),)
