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

from fastapi.testclient import TestClient

from helpers_api import CATALOGUE, DECKS, server
from mtgcoach.api.app import create_app
from wire import decoded, flag, named, number, obj, rows

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404

#: The close code the server uses for a game that is not there.
WS_NO_SUCH_GAME = 4004


def _new_game(client: TestClient) -> str:
    response = client.post("/games", json={"you": "green", "them": "other"})
    assert response.status_code == HTTP_OK
    session_id: str = response.json()["session_id"]
    return session_id


def test_the_decks_it_can_deal() -> None:
    with TestClient(server()) as client:
        assert client.get("/decks").json() == {"decks": ["green", "other"]}


def test_starting_a_game_returns_the_board_and_the_advice() -> None:
    with TestClient(server()) as client:
        body = client.post("/games", json={"you": "green", "them": "other"}).json()
        assert number(body, "state", "turn") == 1
        assert set(obj(body, "advice")) == {"you", "them"}


def test_both_players_get_advice() -> None:
    """One screen at a kitchen table; the defender needs advice too."""
    with TestClient(server()) as client:
        body = client.get(f"/games/{_new_game(client)}").json()
        assert flag(body, "advice", "them", "your_turn") is False
        assert flag(body, "advice", "you", "your_turn") is True


def test_an_unknown_deck_is_refused() -> None:
    with TestClient(server()) as client:
        response = client.post("/games", json={"you": "mono-blue", "them": "green"})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "mono-blue" in response.json()["detail"]


def test_a_game_that_does_not_exist() -> None:
    with TestClient(server()) as client:
        assert client.get("/games/nope").status_code == HTTP_NOT_FOUND


def test_an_event_changes_the_board() -> None:
    with TestClient(server()) as client:
        session_id = _new_game(client)
        body = client.post(
            f"/games/{session_id}/events",
            json={"type": "change_life", "player": "you", "amount": -3},
        ).json()
        assert number(body, "state", "players", "you", "life") == 17


def test_a_malformed_event_is_a_bad_request_with_a_sentence() -> None:
    with TestClient(server()) as client:
        response = client.post(f"/games/{_new_game(client)}/events", json={"type": "atack"})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "unknown event type" in response.json()["detail"]


def test_an_event_the_rules_refuse_is_a_bad_request_too() -> None:
    """Drawing for a player who is not in the game."""
    with TestClient(server()) as client:
        response = client.post(
            f"/games/{_new_game(client)}/events",
            json={"type": "draw_card", "player": "nobody"},
        )
        assert response.status_code == HTTP_BAD_REQUEST


def test_playing_a_creature_as_a_land_is_refused() -> None:
    with TestClient(server()) as client:
        session_id = _new_game(client)
        board = client.get(f"/games/{session_id}").json()
        hand = rows(board, "state", "players", "you", "hand")
        bear = named(hand, "Grizzly Bears")
        response = client.post(
            f"/games/{session_id}/events",
            json={"type": "play_land", "player": "you", "instance_id": bear["instance_id"]},
        )
        assert response.status_code == HTTP_BAD_REQUEST
        assert "not a land" in response.json()["detail"]


def test_an_event_on_a_game_that_does_not_exist() -> None:
    with TestClient(server()) as client:
        response = client.post("/games/nope/events", json={"type": "advance_step"})
        assert response.status_code == HTTP_NOT_FOUND


def test_undo_takes_the_last_event_back() -> None:
    with TestClient(server()) as client:
        session_id = _new_game(client)
        client.post(
            f"/games/{session_id}/events",
            json={"type": "change_life", "player": "you", "amount": -3},
        )
        body = client.post(f"/games/{session_id}/undo").json()
        assert number(body, "state", "players", "you", "life") == 20


def test_undo_on_a_game_that_does_not_exist() -> None:
    with TestClient(server()) as client:
        assert client.post("/games/nope/undo").status_code == HTTP_NOT_FOUND


def test_a_watcher_is_sent_the_board_on_connecting() -> None:
    with TestClient(server()) as client:
        session_id = _new_game(client)
        with client.websocket_connect(f"/games/{session_id}/watch") as socket:
            first = decoded(socket.receive_json())
            assert number(first, "state", "turn") == 1


def test_a_watcher_hears_about_an_event_someone_else_sent() -> None:
    """The whole point of the server: one game, two views."""
    with TestClient(server()) as client:
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
    with TestClient(server()) as client:
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
    with TestClient(server()) as client, client.websocket_connect("/games/nope/watch") as socket:
        message = socket.receive()
        assert message["type"] == "websocket.close"
        assert message["code"] == WS_NO_SUCH_GAME


def test_a_client_that_sends_a_message_is_simply_kept_alive() -> None:
    """The socket is one-way by design; a client ping should not kill it."""
    with TestClient(server()) as client:
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
    with TestClient(create_app(CATALOGUE, {})) as client:
        assert client.get("/decks").json() == {"decks": []}
        assert DECKS
