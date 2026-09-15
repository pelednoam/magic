# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app: the TestClient's response type is opaque to strict
# pyright, and what is read here is read for its shape rather than through
# ``wire``.

"""What each device is sent, which is one hand and one player's advice.

`test_seats` covers what a token may *do*. This is what it may *see*, and the
two are the same fix: the server could not withhold a hand from a device it
could not tell apart from the other one.

Every snapshot used to carry both hands to both devices, twice over -- once in
the board and once in the advice, since a turn report names every card in the
hand it is about. §3's "you cannot see your opponent's hand" held because
nobody looked, which is not a rule being enforced.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from helpers_api import MINE, OTHER_TOKEN, THEIRS, TOKEN, server, talking
from wire import decoded, text

if TYPE_CHECKING:
    from fastapi import FastAPI

#: The decks a test game is dealt, keyed by the seat that gets them.
DEAL = {"you": "green", "them": "other"}

#: What a fresh hand holds (CR 103.4), which is what both counts should read.
OPENING_HAND = 7


def _started(app: FastAPI) -> str:
    """A game, started by the seat `TOKEN` names."""
    with talking(app) as client:
        return text(decoded(client.post("/games", json=DEAL).json()), "session_id")


def test_a_device_is_sent_its_own_hand() -> None:
    app = server()
    game = _started(app)
    with talking(app) as client:
        board = client.get(f"/games/{game}").json()
    assert board["seat"] == MINE
    assert len(board["state"]["players"][MINE]["hand"]) == OPENING_HAND


def test_a_device_is_not_sent_the_other_hand() -> None:
    """Null, not an empty list.

    An empty list says "this player is holding nothing", which is a different
    fact about the game -- and one a player would act on.
    """
    app = server()
    game = _started(app)
    with talking(app) as client:
        board = client.get(f"/games/{game}").json()
    assert board["state"]["players"][THEIRS]["hand"] is None


def test_how_many_cards_the_other_player_holds_is_still_sent() -> None:
    """Public information (CR 400.2 hides the contents, not the count).

    It is what a player at a table actually counts, so hiding the list costs
    the tracker nothing it should have had.
    """
    app = server()
    game = _started(app)
    with talking(app) as client:
        board = client.get(f"/games/{game}").json()
    assert board["state"]["players"][THEIRS]["hand_size"] == OPENING_HAND


def test_the_advice_is_for_the_asking_seat_only() -> None:
    """A turn report names every card in the hand it is about.

    So advice for both players was the opponent's hand arriving twice over:
    once in the board and once in the advice.
    """
    app = server()
    game = _started(app)
    with talking(app) as client:
        board = client.get(f"/games/{game}").json()
    assert set(board["advice"]) == {MINE}


def test_the_other_device_gets_the_mirror_image() -> None:
    """Each sees its own hand and not the other's. One game, two views."""
    app = server()
    game = _started(app)
    with talking(app, token=OTHER_TOKEN) as client:
        board = client.get(f"/games/{game}").json()
    assert board["seat"] == THEIRS
    assert board["state"]["players"][THEIRS]["hand"] is not None
    assert board["state"]["players"][MINE]["hand"] is None
    assert set(board["advice"]) == {THEIRS}


# --- and the same on the socket ----------------------------------------------


def test_the_socket_sends_each_seat_its_own_board() -> None:
    """The socket is the connection that streams the whole board.

    It used to send one payload to every watcher, so whichever device had the
    token was sent both hands on every change.
    """
    app = server()
    game = _started(app)
    stranger = TestClient(app)
    with stranger.websocket_connect(f"/games/{game}/watch?token={OTHER_TOKEN}") as socket:
        board = socket.receive_json()
    assert board["seat"] == THEIRS
    assert board["state"]["players"][MINE]["hand"] is None


def test_a_broadcast_reaches_both_seats_with_their_own_hands() -> None:
    """One event, two payloads. They differ only in which hand they carry."""
    app = server()
    game = _started(app)
    watching = TestClient(app)
    with (
        watching.websocket_connect(f"/games/{game}/watch?token={TOKEN}") as mine,
        watching.websocket_connect(f"/games/{game}/watch?token={OTHER_TOKEN}") as theirs,
    ):
        mine.receive_json()
        theirs.receive_json()
        with talking(app) as client:
            client.post(
                f"/games/{game}/events",
                json={"type": "change_life", "player": MINE, "amount": -1},
            )
        first, second = mine.receive_json(), theirs.receive_json()
    assert first["state"]["players"][MINE]["hand"] is not None
    assert first["state"]["players"][THEIRS]["hand"] is None
    assert second["state"]["players"][THEIRS]["hand"] is not None
    assert second["state"]["players"][MINE]["hand"] is None
