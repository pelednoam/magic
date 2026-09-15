# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module, like every
# other test that drives a real client.

"""Casting a spell the way the app does, over HTTP.

The test that was missing. Casting worked in the harness, which calls the
reducer directly, and was refused by every server -- because the app sent the
payment taps as separate events first and the guard then recomputed the
available mana with those lands already tapped. Nothing exercised the HTTP path
end to end, so nothing said so.

The shape here is exactly `playing.ts`: one cast carrying its payment, then a
resolve. If these two disagree with that file, one of them is wrong.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import server, talking
from wire import decoded, named, rows, text

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200
HTTP_REFUSED = 400

#: How many Forests a Grizzly Bears takes.
PAID_WITH = 2


def _started(client: TestClient) -> str:
    """A new game, and what it is called."""
    created = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
    session = created["session_id"]
    assert isinstance(session, str)
    return session


def _to_main(client: TestClient, session: str) -> dict[str, object]:
    """Walk to the first main phase, where a land can be played."""
    body = decoded(client.get(f"/games/{session}").json())
    while text(body, "state", "step") != "precombat_main":
        body = _sent(client, session, {"type": "advance_step"})
    return body


def _sent(client: TestClient, session: str, event: dict[str, object]) -> dict[str, object]:
    """Apply one event and hand back the board it produced."""
    sent = client.post(f"/games/{session}/events", json=event)
    assert sent.status_code == HTTP_OK, sent.text
    return decoded(sent.json())


def _forests(body: dict[str, object]) -> list[dict[str, object]]:
    """Every Forest in your hand."""
    hand = rows(body, "state", "players", "you", "hand")
    return [card for card in hand if card["name"] == "Forest"]


def test_a_spell_can_be_cast_over_http() -> None:
    """Which it could not, for as long as the payment was sent separately.

    Two Forests down, then a Grizzly Bears cast by tapping both. The server
    used to answer "you need 2 more untapped sources" -- having tapped them
    itself, one event earlier.
    """
    with talking(server()) as client:
        session = _started(client)
        body = _to_main(client, session)

        # A land this turn, and a second put down directly so there are two to
        # tap. (One land drop a turn is the rule; `move_card` is the primitive
        # that bypasses it, which is what it is for.)
        forests = _forests(body)
        body = _sent(
            client,
            session,
            {"type": "play_land", "player": "you", "instance_id": forests[0]["instance_id"]},
        )
        body = _sent(
            client,
            session,
            {
                "type": "move_card",
                "player": "you",
                "instance_id": forests[1]["instance_id"],
                "to": "battlefield",
            },
        )

        bear = named(rows(body, "advice", "you", "hand"), "Grizzly Bears")
        assert bear["playable"] is True, bear["reasons"]
        payment = bear["payment"]
        assert isinstance(payment, dict)

        cast = client.post(
            f"/games/{session}/events",
            json={
                "type": "cast_spell",
                "player": "you",
                "instance_id": bear["instance_id"],
                "payment": payment["tap"],
            },
        )
        assert cast.status_code == HTTP_OK, cast.text
        body = decoded(cast.json())
        # On the stack, and the lands it named are tapped -- one action.
        assert [c["name"] for c in rows(body, "state", "players", "you", "stack")] == [
            "Grizzly Bears"
        ]
        board = rows(body, "state", "players", "you", "battlefield")
        assert sum(1 for permanent in board if permanent["tapped"]) == PAID_WITH

        resolved = client.post(
            f"/games/{session}/events",
            json={
                "type": "resolve_spell",
                "player": "you",
                "instance_id": bear["instance_id"],
                "to": "battlefield",
            },
        )
        assert resolved.status_code == HTTP_OK, resolved.text
        body = decoded(resolved.json())
        assert rows(body, "state", "players", "you", "stack") == []
        assert "Grizzly Bears" in {
            p["name"] for p in rows(body, "state", "players", "you", "battlefield")
        }


def test_a_cast_that_pays_with_nothing_is_refused() -> None:
    """The hole the separate-taps version left open: casting for free."""
    with talking(server()) as client:
        session = _started(client)
        body = _to_main(client, session)
        bear = named(rows(body, "state", "players", "you", "hand"), "Grizzly Bears")
        refused = client.post(
            f"/games/{session}/events",
            json={"type": "cast_spell", "player": "you", "instance_id": bear["instance_id"]},
        )
        assert refused.status_code == HTTP_REFUSED
        assert "Grizzly Bears" in refused.text
