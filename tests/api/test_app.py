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

from helpers_api import CATALOGUE, TOKEN, NoAnswers, NoCoach, server, talking
from mtgcoach.api.app import create_app
from mtgcoach.api.context import Claude
from wire import decoded, flag, named, number, obj, rows

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

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
    with talking(server()) as client:
        assert client.get("/decks").json() == {"decks": ["green", "other"]}


def test_starting_a_game_returns_the_board_and_the_advice() -> None:
    with talking(server()) as client:
        body = client.post("/games", json={"you": "green", "them": "other"}).json()
        assert number(body, "state", "turn") == 1
        assert set(obj(body, "advice")) == {"you", "them"}


def test_both_players_get_advice() -> None:
    """One screen at a kitchen table; the defender needs advice too."""
    with talking(server()) as client:
        body = client.get(f"/games/{_new_game(client)}").json()
        assert flag(body, "advice", "them", "your_turn") is False
        assert flag(body, "advice", "you", "your_turn") is True


def test_an_unknown_deck_is_refused() -> None:
    with talking(server()) as client:
        response = client.post("/games", json={"you": "mono-blue", "them": "green"})
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
    """Drawing for a player who is not in the game."""
    with talking(server()) as client:
        response = client.post(
            f"/games/{_new_game(client)}/events",
            json={"type": "draw_card", "player": "nobody"},
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


def test_undo_takes_the_last_event_back() -> None:
    with talking(server()) as client:
        session_id = _new_game(client)
        client.post(
            f"/games/{session_id}/events",
            json={"type": "change_life", "player": "you", "amount": -3},
        )
        body = client.post(f"/games/{session_id}/undo").json()
        assert number(body, "state", "players", "you", "life") == 20


def test_undo_on_a_game_that_does_not_exist() -> None:
    with talking(server()) as client:
        assert client.post("/games/nope/undo").status_code == HTTP_NOT_FOUND


def test_the_version_only_ever_goes_up() -> None:
    """It is the client's only ordering, and undo is a change like any other.

    Counting *events* made it go backwards on undo -- and the client keeps a
    snapshot unless the new one is at least as new, so it discarded every undo
    and undo silently did nothing. This test used to pin that: it asserted the
    undo snapshot came back as 0.
    """
    with talking(server()) as client:
        session_id = _new_game(client)
        seen = [number(decoded(client.get(f"/games/{session_id}").json()), "version")]
        seen.append(
            number(
                decoded(
                    client.post(
                        f"/games/{session_id}/events",
                        json={"type": "change_life", "player": "you", "amount": -1},
                    ).json()
                ),
                "version",
            )
        )
        seen.append(number(decoded(client.post(f"/games/{session_id}/undo").json()), "version"))
        assert seen == sorted(seen), f"versions went backwards: {seen}"
        assert len(set(seen)) == len(seen), f"two states shared a version: {seen}"


def test_an_undo_is_newer_than_the_event_it_undid() -> None:
    """Otherwise the client cannot tell the undo from the thing being undone."""
    with talking(server()) as client:
        session_id = _new_game(client)
        after = decoded(
            client.post(
                f"/games/{session_id}/events",
                json={"type": "change_life", "player": "you", "amount": -1},
            ).json()
        )
        undone = decoded(client.post(f"/games/{session_id}/undo").json())
        assert number(undone, "version") > number(after, "version")
        assert number(undone, "state", "players", "you", "life") == 20


def test_a_deck_too_short_to_deal_is_a_bad_request() -> None:
    """A partial import can advertise a deck of six. That is a thing to say."""
    short = create_app(CATALOGUE, {"tiny": ("Forest",) * 3}, TOKEN, Claude(NoCoach(), NoAnswers()))
    with talking(short) as client:
        response = client.post("/games", json={"you": "tiny", "them": "tiny"})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "opening hand" in response.json()["detail"]


def test_the_browser_build_is_allowed_to_talk_to_the_server() -> None:
    """It is served from another port, so every request is cross-origin."""
    with talking(server()) as client:
        response = client.get("/decks", headers={"Origin": "http://localhost:8081"})
        assert response.headers.get("access-control-allow-origin") == "*"
