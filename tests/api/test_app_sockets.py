# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module on purpose:
# everything it returns is narrowed by ``wire``, so no test past here works with
# an unknown type.

"""Watching a game over a socket, driven by a real client.

The part a unit test cannot see: whether a second client watching a game
actually hears about an event it did not send.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import CATALOGUE, DECKS, SEATING, server, talking
from helpers_fakes import NoAnswers, NoCoach
from mtgcoach.api.app import create_app
from mtgcoach.api.context import Claude
from wire import decoded, number

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404

#: The close code the server uses for a game that is not there.
WS_NO_SUCH_GAME = 4004


def _new_game(client: TestClient) -> str:
    response = client.post("/games", json={"mine": "green", "theirs": "other"})
    assert response.status_code == HTTP_OK
    session_id: str = response.json()["session_id"]
    return session_id


def test_a_watcher_is_sent_the_board_on_connecting() -> None:
    with talking(server()) as client:
        session_id = _new_game(client)
        with client.websocket_connect(f"/games/{session_id}/watch") as socket:
            first = decoded(socket.receive_json())
            assert number(first, "state", "turn") == 1


def test_a_watcher_hears_about_an_event_someone_else_sent() -> None:
    """The whole point of the server: one game, two views."""
    with talking(server()) as client:
        session_id = _new_game(client)
        with client.websocket_connect(f"/games/{session_id}/watch") as socket:
            socket.receive_json()
            client.post(
                f"/games/{session_id}/events",
                json={"type": "change_life", "player": "you", "amount": -4},
            )
            update = decoded(socket.receive_json())
            assert number(update, "state", "players", "you", "life") == 16


def test_a_watcher_hears_about_an_undo_too() -> None:
    with talking(server()) as client:
        session_id = _new_game(client)
        client.post(
            f"/games/{session_id}/events",
            json={"type": "change_life", "player": "you", "amount": -4},
        )
        with client.websocket_connect(f"/games/{session_id}/watch") as socket:
            socket.receive_json()
            client.post(f"/games/{session_id}/undo")
            undone = decoded(socket.receive_json())
            assert number(undone, "state", "players", "you", "life") == 20


def test_watching_a_game_that_does_not_exist_closes_the_socket() -> None:
    """With a code the client can act on, rather than an empty stream."""
    with talking(server()) as client, client.websocket_connect("/games/nope/watch") as socket:
        message = socket.receive()
        assert message["type"] == "websocket.close"
        assert message["code"] == WS_NO_SUCH_GAME


def test_a_client_that_sends_a_message_is_simply_kept_alive() -> None:
    """The socket is one-way by design; a client ping should not kill it."""
    with talking(server()) as client:
        session_id = _new_game(client)
        with client.websocket_connect(f"/games/{session_id}/watch") as socket:
            socket.receive_json()
            socket.send_text("ping")
            client.post(
                f"/games/{session_id}/events",
                json={"type": "change_life", "player": "you", "amount": -1},
            )
            after = decoded(socket.receive_json())
            assert number(after, "state", "players", "you", "life") == 19


def test_a_server_with_no_decks_still_starts() -> None:
    with talking(create_app(CATALOGUE, {}, SEATING, Claude(NoCoach(), NoAnswers()))) as client:
        assert client.get("/decks").json() == {"decks": []}
        assert DECKS
