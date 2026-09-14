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
``apps/mobile/src/wire/``, in both directions: a field the server sends that
the app has never heard of, and a field the app declares that the server no
longer sends. Either is a bug; neither raises anything at runtime.
"""

from __future__ import annotations

import pytest

from helpers_api import RULES, Answering, Canned, server, talking
from mtgcoach.coach.advice import Explanation
from mtgcoach.rules.answer import Answer
from wire import decoded, named, rows, text
from wirefields import DYNAMIC_KEYS, declared, keys, wire_files

#: The status the server returns when an event was accepted.
HTTP_OK = 200

#: Enough advances to walk a whole turn and into the next player's.
STEPS_IN_A_TURN = 26


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
    # A canned answer carrying every field, so the coach route contributes its
    # whole shape. The words are never read here -- `views.explanation` emits
    # all six keys whatever they hold -- but an empty one would be indistinguish-
    # able from a route that had stopped sending them.
    said = Explanation(
        because="because",
        in_short="in short",
        watch_out=("watch out",),
        check_yourself=("check yourself",),
    )
    answer = Answer(
        answer="Lethal damage first, then the rest goes through.",
        in_short="Some gets through.",
        citations=("702.19b",),
        unsure="not everything",
    )
    with talking(server(explainer=Canned(said), asker=Answering(answer), rules=RULES)) as client:
        created = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
        session_id = created["session_id"]
        assert isinstance(session_id, str)
        found.update(keys(created))

        def act(**event: object) -> dict[str, object]:
            response = client.post(f"/games/{session_id}/events", json=event)
            assert response.status_code == HTTP_OK, response.text
            body = decoded(response.json())
            found.update(keys(body))
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
        # On to a main phase, because a land drop is only legal there and the
        # server now refuses what the coach refuses.
        while text(body, "state", "step") != "precombat_main":
            body = act(type="advance_step")
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

        # The coach route, whose payload is a different shape from the snapshot
        # and reaches the same screen.
        coached = client.post(f"/games/{session_id}/coach", json={"player": "you"})
        assert coached.status_code == HTTP_OK, coached.text
        found.update(keys(decoded(coached.json())))

        # And the rules question route, whose payload carries the retrieved
        # passages as well as the answer.
        asked = client.post(
            f"/games/{session_id}/ask",
            json={"player": "you", "question": "how does trample work?"},
        )
        assert asked.status_code == HTTP_OK, asked.text
        found.update(keys(decoded(asked.json())))
    return frozenset(found)


def _is(card: dict[str, object], name: str) -> bool:
    """Whether this card is the one named."""
    return card.get("name") == name


def test_the_app_knows_every_field_the_server_sends(sent: frozenset[str]) -> None:
    """A field the app has never heard of is a blank space in the UI."""
    assert (sent - DYNAMIC_KEYS) - declared() == set()


def test_the_server_sends_every_field_the_app_declares(sent: frozenset[str]) -> None:
    """A field the app expects and no longer gets is the same bug, mirrored."""
    assert declared() - sent == set()


def test_the_wire_folder_is_where_it_is_thought_to_be() -> None:
    """A moved or renamed module would make both checks vacuously pass."""
    assert wire_files() == ["board.ts", "claude.ts", "index.ts", "shapes.ts"]


def test_the_turn_actually_covers_the_payload(sent: frozenset[str]) -> None:
    """Guard on the guard: a turn that reached nothing would check nothing."""
    corners = {
        "tapped",
        "they_lose",
        "tap",
        "keep",
        "event",
        "payment",
        "unknown",
        "check_yourself",
        "citations",
        "reference",
    }
    assert corners <= sent
