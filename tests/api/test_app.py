# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module on purpose:
# everything it returns is narrowed by ``wire``, so no test past here works with
# an unknown type.

"""The HTTP and WebSocket surface, driven by a real client.

Thin as the module is, the things that can be wrong here are the ones a unit
test cannot see: status codes, the shape on the wire, and whether a second
client watching actually hears anything.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import CATALOGUE, SEATING, server, talking
from helpers_fakes import NoAnswers, NoCoach
from mtgcoach.api.app import create_app
from mtgcoach.api.context import Claude
from wire import flag, named, number, obj, rows

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


def test_the_decks_it_can_deal() -> None:
    with talking(server()) as client:
        assert client.get("/decks").json() == {"decks": ["green", "other"]}


def test_starting_a_game_returns_the_board_and_the_advice() -> None:
    with talking(server()) as client:
        body = client.post("/games", json={"mine": "green", "theirs": "other"}).json()
        assert number(body, "state", "turn") == 1
        assert set(obj(body, "advice")) == {"you"}


def test_the_advice_is_the_asking_seat_s_own() -> None:
    """It used to be both. The defender has their own device. See `test_hidden`."""
    with talking(server()) as client:
        body = client.get(f"/games/{_new_game(client)}").json()
        assert set(obj(body, "advice")) == {"you"}
        assert flag(body, "advice", "you", "your_turn") is True


def test_an_unknown_deck_is_refused() -> None:
    with talking(server()) as client:
        response = client.post("/games", json={"mine": "mono-blue", "theirs": "green"})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "mono-blue" in response.json()["detail"]


def test_a_game_that_does_not_exist() -> None:
    with talking(server()) as client:
        assert client.get("/games/nope").status_code == HTTP_NOT_FOUND


def test_an_event_changes_the_board() -> None:
    with talking(server()) as client:
        session_id = _new_game(client)
        body = client.post(
            f"/games/{session_id}/events",
            json={"type": "change_life", "player": "you", "amount": -3},
        ).json()
        assert number(body, "state", "players", "you", "life") == 17


def test_a_malformed_event_is_a_bad_request_with_a_sentence() -> None:
    with talking(server()) as client:
        response = client.post(f"/games/{_new_game(client)}/events", json={"type": "atack"})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "unknown event type" in response.json()["detail"]


def test_an_event_the_rules_refuse_is_a_bad_request_too() -> None:
    """Resolving a spell that is not on the stack.

    It used to be drawing for a player who is not in the game -- a 403 now,
    since the seat is checked before the engine is asked anything. So this
    needs an event the *rules* refuse from the seat that sent it.
    """
    with talking(server()) as client:
        response = client.post(
            f"/games/{_new_game(client)}/events",
            json={
                "type": "resolve_spell",
                "player": "you",
                "instance_id": "nothing-is-waiting",
                "to": "graveyard",
            },
        )
        assert response.status_code == HTTP_BAD_REQUEST


def test_playing_a_creature_as_a_land_is_refused() -> None:
    with talking(server()) as client:
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
    with talking(server()) as client:
        response = client.post("/games/nope/events", json={"type": "advance_step"})
        assert response.status_code == HTTP_NOT_FOUND


def test_a_deck_too_short_to_deal_is_a_bad_request() -> None:
    """A partial import can advertise a deck of six. That is a thing to say."""
    short = create_app(
        CATALOGUE, {"tiny": ("Forest",) * 3}, SEATING, Claude(NoCoach(), NoAnswers())
    )
    with talking(short) as client:
        response = client.post("/games", json={"mine": "tiny", "theirs": "tiny"})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "opening hand" in response.json()["detail"]


def test_the_browser_build_is_allowed_to_talk_to_the_server() -> None:
    """It is served from another port, so every request is cross-origin."""
    with talking(server()) as client:
        response = client.get("/decks", headers={"Origin": "http://localhost:8081"})
        assert response.headers.get("access-control-allow-origin") == "*"
