# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module, like every
# other test that drives a real client.

"""Answering a spell, over HTTP, from both seats -- and from both devices.

Split from ``test_app_casting`` because it is a different claim. That file says
one player can cast a spell and let it resolve; this one says the *other*
player gets a turn in between -- which is the thing the app did not have, and
the thing a nine-year-old is here to learn.

Every step of it goes through the real routes, because the sequence is the
finding. The old engine accepted a cast and a resolution back to back, and
accepted resolving the spell cast *first* when there were two -- so a test that
skipped to "there are two spells on the stack" would be assuming away exactly
what was broken.

Two clients, one per seat. It used to be one, reading both hands and both
players' advice off a single board and acting for either player -- which is
what a token per seat took away. This is the test that most needed two devices
and is the closest thing here to a real table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from driving import HTTP_OK, HTTP_REFUSED, device, forests, sent, started, walked
from helpers_api import THEIRS, server, talking
from wire import decoded, named, rows

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx import Response


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


def test_the_other_player_can_answer_before_the_spell_resolves() -> None:
    """The window R04 is about, over the wire, from both seats.

    You cast a creature; they answer with a trick. Theirs went on the stack
    last, so theirs resolves first (CR 405.2, CR 405.5, CR 117.7) -- and asking
    for yours instead is refused. The old per-player stack had two orders and
    no way to compare them, so this sequence put the creature down first and
    the server agreed.
    """
    with talking(server()) as client:
        session = started(client)
        body = walked(client, session, "precombat_main")
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
        # A Forest for them too, so they can afford the answer -- read from
        # *their* device, because the board this one is sent does not carry
        # their hand.
        answering = device(client, THEIRS)
        mine = body
        body = decoded(answering.get(f"/games/{session}").json())
        theirs = named(rows(body, "state", "players", "them", "hand"), "Forest")
        body = sent(
            client,
            session,
            {
                "type": "move_card",
                "player": "them",
                "instance_id": theirs["instance_id"],
                "to": "battlefield",
            },
        )

        bear = named(rows(mine, "advice", "you", "hand"), "Grizzly Bears")
        assert isinstance(bear["payment"], dict)
        body = sent(
            client,
            session,
            {
                "type": "cast_spell",
                "player": "you",
                "instance_id": bear["instance_id"],
                "payment": bear["payment"]["tap"],
            },
        )
        sent(client, session, {"type": "pass_priority", "player": "you"})
        body = decoded(answering.get(f"/games/{session}").json())
        growth = named(rows(body, "advice", "them", "hand"), "Giant Growth")
        assert growth["playable"] is True, growth["reasons"]
        assert isinstance(growth["payment"], dict)
        body = sent(
            client,
            session,
            {
                "type": "cast_spell",
                "player": "them",
                "instance_id": growth["instance_id"],
                "payment": growth["payment"]["tap"],
            },
        )
        # One order, bottom first, and both seats read the same list.
        assert [c["name"] for c in rows(body, "state", "stack")] == [
            "Grizzly Bears",
            "Giant Growth",
        ]

        for seat in ("them", "you"):
            sent(client, session, {"type": "pass_priority", "player": seat})
        out_of_order = _resolving(client, session, bear["instance_id"])
        assert out_of_order.status_code == HTTP_REFUSED
        assert "not the top of the stack" in out_of_order.text

        answered = answering.post(
            f"/games/{session}/events",
            json={
                "type": "resolve_spell",
                "player": "them",
                "instance_id": growth["instance_id"],
                "to": "graveyard",
            },
        )
        assert answered.status_code == HTTP_OK, answered.text
        body = decoded(answered.json())
        assert [c["name"] for c in rows(body, "state", "stack")] == ["Grizzly Bears"]
        assert "Giant Growth" in {
            c["name"] for c in rows(body, "state", "players", "them", "graveyard")
        }


def test_a_cast_that_pays_with_nothing_is_refused() -> None:
    """The hole the separate-taps version left open: casting for free."""
    with talking(server()) as client:
        session = started(client)
        body = walked(client, session, "precombat_main")
        bear = named(rows(body, "state", "players", "you", "hand"), "Grizzly Bears")
        refused = client.post(
            f"/games/{session}/events",
            json={"type": "cast_spell", "player": "you", "instance_id": bear["instance_id"]},
        )
        assert refused.status_code == HTTP_REFUSED
        assert "Grizzly Bears" in refused.text
