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

The shape here is exactly `playing.ts`, which now sends the cast and *stops*:
a spell resolves because every player has passed in succession (CR 117.4), so
the resolution is two passes and a deliberate act later. If these tests and
that file disagree, one of them is wrong.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from driving import HTTP_OK, HTTP_REFUSED, forests, sent, started, walked
from helpers_api import server, talking
from wire import at, decoded, named, rows, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx import Response

#: How many Forests a Grizzly Bears takes.
PAID_WITH = 2


def test_a_spell_can_be_cast_over_http() -> None:
    """Which it could not, for as long as the payment was sent separately.

    Two Forests down, then a Grizzly Bears cast by tapping both. The server
    used to answer "you need 2 more untapped sources" -- having tapped them
    itself, one event earlier.
    """
    with talking(server()) as client:
        session = started(client)
        body = walked(client, session, "precombat_main")

        # A land this turn, and a second put down directly so there are two to
        # tap. (One land drop a turn is the rule; `move_card` is the primitive
        # that bypasses it, which is what it is for.)
        green = forests(body)
        body = sent(
            client,
            session,
            {"type": "play_land", "player": "you", "instance_id": green[0]["instance_id"]},
        )
        body = sent(
            client,
            session,
            {
                "type": "move_card",
                "player": "you",
                "instance_id": green[1]["instance_id"],
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
        # On the one shared stack, attributed, and with somewhere to go that
        # the server worked out rather than the client remembering it.
        (waiting,) = rows(body, "state", "stack")
        assert waiting["name"] == "Grizzly Bears"
        assert waiting["controller"] == "you"
        assert waiting["resolves_to"] == "battlefield"
        # The lands it named are tapped -- one action (CR 601.2).
        board = rows(body, "state", "players", "you", "battlefield")
        assert sum(1 for permanent in board if permanent["tapped"]) == PAID_WITH
        # And the caster still holds priority (CR 117.3c), so they may answer
        # their own spell before letting it go.
        assert text(body, "state", "priority") == "you"

        # Resolving now is refused: the other player has not been asked.
        early = _resolving(client, session, bear["instance_id"])
        assert early.status_code == HTTP_REFUSED
        assert "does not resolve until" in early.text

        for seat in ("you", "them"):
            passed = sent(client, session, {"type": "pass_priority", "player": seat})
        assert at(passed, "state", "priority") is None
        assert words(passed, "state", "passed") == ["you", "them"]

        resolved = _resolving(client, session, bear["instance_id"])
        assert resolved.status_code == HTTP_OK, resolved.text
        body = decoded(resolved.json())
        assert rows(body, "state", "stack") == []
        assert "Grizzly Bears" in {
            p["name"] for p in rows(body, "state", "players", "you", "battlefield")
        }
        # Priority goes back to the active player (CR 117.3b).
        assert text(body, "state", "priority") == "you"


def _resolving(client: TestClient, session: str, instance_id: object) -> Response:
    """Ask for the top of the stack to resolve, without insisting it works."""
    sent: Response = client.post(
        f"/games/{session}/events",
        json={
            "type": "resolve_spell",
            "player": "you",
            "instance_id": instance_id,
            "to": "battlefield",
        },
    )
    return sent
