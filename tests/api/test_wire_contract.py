# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""The server's JSON and the app's types, checked against each other.

Both are written by hand, which is the right call -- the wire is a contract two
sides agreed on, not a dump of either's internals -- and it means the two can
drift apart silently. The failure that causes is a blank space in the UI, found
at the kitchen table rather than in CI.

So this builds a real snapshot from the real views and reads
``apps/mobile/src/wire.ts``, in both directions: a field the server sends that
the app has never heard of, and a field the app declares that the server no
longer sends. Either is a bug; neither raises anything at runtime.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from helpers_api import server

from wire import decoded, named, rows

if TYPE_CHECKING:
    from collections.abc import Iterator

WIRE_TS = Path(__file__).resolve().parents[2] / "apps" / "mobile" / "src" / "wire.ts"

#: Keys that are data rather than fields: the server maps player ids to their
#: state, and those ids are values the app reads at runtime, not names it can
#: declare. Everything else in the payload is a field with a type.
DYNAMIC_KEYS = frozenset({"you", "them"})

#: Declared by the app for a route this fixture does not exercise.
CLIENT_ONLY = frozenset({"session_id"})

#: The status the server returns when an event was accepted.
HTTP_OK = 200

#: Enough advances to walk a whole turn and into the next player's.
STEPS_IN_A_TURN = 26

#: `readonly name: ...` in a TypeScript interface.
FIELD = re.compile(r"^\s*readonly\s+(\w+)\??:", re.MULTILINE)


@pytest.fixture(scope="module")
def sent() -> frozenset[str]:
    """Every field the server sends anywhere across a turn actually played.

    One payload cannot carry the whole shape: attack plans exist only in the
    declare-attackers step and reminders only at an upkeep, and a permanent is
    only `tapped` once something has tapped it. So this plays a turn and unions
    what it sees -- which is also the honest question, since the contract is
    "what does this server ever send", not "what is in one response".
    """
    found: set[str] = set()
    with TestClient(server()) as client:
        created = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
        session_id = created["session_id"]
        assert isinstance(session_id, str)
        found.update(_keys(created))

        def act(**event: object) -> dict[str, object]:
            response = client.post(f"/games/{session_id}/events", json=event)
            assert response.status_code == HTTP_OK, response.text
            body = decoded(response.json())
            found.update(_keys(body))
            return body

        body = act(type="advance_step")
        # A creature each, so an attack has something to kill, and a trigger
        # on the table so an upkeep has something to remind you about.
        for player in ("you", "them"):
            bear = named(rows(body, "state", "players", player, "hand"), "Grizzly Bears")
            body = act(
                type="move_card", player=player, instance_id=bear["instance_id"], to="battlefield"
            )
        bell = named(rows(body, "state", "players", "you", "hand"), "Bell-Ringer")
        body = act(
            type="move_card", player="you", instance_id=bell["instance_id"], to="battlefield"
        )
        # Two Forests: one played and tapped, one left up so a spell in hand
        # comes back with a payment on it.
        forests = [c for c in rows(body, "state", "players", "you", "hand") if _is(c, "Forest")]
        body = act(type="play_land", player="you", instance_id=forests[0]["instance_id"])
        body = act(
            type="move_card", player="you", instance_id=forests[1]["instance_id"], to="battlefield"
        )
        act(type="set_tapped", player="you", instance_id=forests[0]["instance_id"], tapped=True)

        for _ in range(STEPS_IN_A_TURN):
            act(type="advance_step")
    return frozenset(found)


def _is(card: dict[str, object], name: str) -> bool:
    """Whether this card is the one named."""
    return card.get("name") == name


def _keys(value: object) -> Iterator[str]:
    """Every field name anywhere in a payload."""
    if isinstance(value, dict):
        for key, nested in value.items():  # pyright: ignore[reportUnknownVariableType]
            assert isinstance(key, str)
            yield key
            yield from _keys(nested)
    elif isinstance(value, list):
        for item in value:  # pyright: ignore[reportUnknownVariableType]
            yield from _keys(item)


def _declared() -> frozenset[str]:
    """Every field the app's types declare."""
    return frozenset(FIELD.findall(WIRE_TS.read_text(encoding="utf-8")))


def test_the_app_knows_every_field_the_server_sends(sent: frozenset[str]) -> None:
    """A field the app has never heard of is a blank space in the UI."""
    assert (sent - DYNAMIC_KEYS) - _declared() == set()


def test_the_server_sends_every_field_the_app_declares(sent: frozenset[str]) -> None:
    """A field the app expects and no longer gets is the same bug, mirrored."""
    assert _declared() - sent - CLIENT_ONLY == set()


def test_the_turn_actually_covers_the_payload(sent: frozenset[str]) -> None:
    """Guard on the guard: a turn that reached nothing would check nothing."""
    corners = {"tapped", "they_lose", "tap", "keep", "event", "payment", "unknown"}
    assert corners <= sent
