"""Driving the server, and reading what it says back."""

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module on purpose:
# everything it returns is narrowed by ``wire``, so no test past here works with
# an unknown type.

from __future__ import annotations

from typing import TYPE_CHECKING

from wire import by_name, decoded, named, obj, rows, text

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_BAD_REQUEST = 400

#: Enough advances to reach the other player's combat from anywhere.
STEPS_IN_TWO_TURNS = 24


def start(client: TestClient) -> str:
    """Begin a game and return its name."""
    response = client.post("/games", json={"you": "green", "them": "white"})
    assert response.status_code == HTTP_OK, response.text
    return text(decoded(response.json()), "session_id")


def send(client: TestClient, session_id: str, **event: object) -> dict[str, object]:
    """Send one event and return the snapshot it produced."""
    response = client.post(f"/games/{session_id}/events", json=event)
    assert response.status_code == HTTP_OK, response.text
    return decoded(response.json())


def look(client: TestClient, session_id: str) -> dict[str, object]:
    """The snapshot as it stands."""
    response = client.get(f"/games/{session_id}")
    assert response.status_code == HTTP_OK, response.text
    return decoded(response.json())


def zone(body: dict[str, object], player: str, name: str) -> list[dict[str, object]]:
    """One player's cards in one zone."""
    return rows(body, "state", "players", player, name)


def card(body: dict[str, object], player: str, name: str, printed: str) -> dict[str, object]:
    """The one card of that name in that zone."""
    return named(zone(body, player, name), printed)


def verdicts(body: dict[str, object], player: str) -> dict[str, dict[str, object]]:
    """What the coach says about each card in hand, keyed by name."""
    return by_name(rows(body, "advice", player, "hand"))


def advice(body: dict[str, object], player: str) -> dict[str, object]:
    """One player's whole turn report."""
    return obj(body, "advice", player)


def board(body: dict[str, object], player: str) -> dict[str, object]:
    """One player's half of the board."""
    return obj(body, "state", "players", player)


def undo(client: TestClient, session_id: str) -> dict[str, object]:
    """Take back the last event and return the snapshot it left."""
    response = client.post(f"/games/{session_id}/undo")
    assert response.status_code == HTTP_OK, response.text
    return decoded(response.json())


def refuse(client: TestClient, session_id: str, **event: object) -> str:
    """Send an event the server should reject, and return the reason it gave."""
    response = client.post(f"/games/{session_id}/events", json=event)
    assert response.status_code == HTTP_BAD_REQUEST, response.text
    return text(decoded(response.json()), "detail")
