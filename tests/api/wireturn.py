# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""One turn, actually played, walked for every field name it produces.

The bulk of the wire contract. One payload cannot carry the whole shape --
attack plans exist only in the declare-attackers step, reminders only at an
upkeep, the stack's own fields only while a spell is waiting, and a permanent
is only `tapped` once something has tapped it -- so this plays through all of
those and unions what it sees.

Which makes the *sequence* load-bearing, and it is written out rather than
short-cut for that reason. A spell reaches the stack by being cast by a player
who holds priority (CR 117.1a) and leaves it because both players passed
(CR 117.4); a step ends the same way (CR 500.2). Assembling a board with a
spell on it would have covered the fields and exercised none of that.

``wirecorners`` has the two shapes a turn never reaches, and
``test_wire_contract`` is where the sets get compared.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from driving import HTTP_OK, stepped
from helpers_api import RULES, Answering, Canned, server, talking
from mtgcoach.coach.advice import Explanation
from mtgcoach.rules.answer import Answer
from wire import decoded, named, rows, text
from wirefields import keys

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

#: Enough step endings to walk a whole turn and into the next player's.
STEPS_IN_A_TURN = 26


def a_whole_turn() -> set[str]:
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

        body = _stepped(client, session_id, found)
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
            body = _stepped(client, session_id, found)
        # Two Forests: one played and tapped, one left up so a spell in hand
        # comes back with a payment on it.
        forests = [c for c in rows(body, "state", "players", "you", "hand") if _is(c, "Forest")]
        body = act(type="play_land", player="you", instance_id=forests[0]["instance_id"])
        body = act(
            type="move_card", player="you", instance_id=forests[1]["instance_id"], to="battlefield"
        )
        act(type="set_tapped", player="you", instance_id=forests[0]["instance_id"], tapped=True)

        # A spell onto the stack and off it again, because the stack's own
        # fields -- `controller`, `resolves_to` -- exist nowhere else in the
        # payload, and a contract test that never cast anything declared them
        # covered while never once seeing one. Both passes go through the wire
        # too: a spell resolves because every player passed (CR 117.4).
        growth = named(rows(body, "state", "players", "you", "hand"), "Giant Growth")
        act(
            type="cast_spell",
            player="you",
            instance_id=growth["instance_id"],
            payment=[forests[1]["instance_id"]],
        )
        for seat in ("you", "them"):
            act(type="pass_priority", player=seat)
        body = act(
            type="resolve_spell",
            player="you",
            instance_id=growth["instance_id"],
            to="graveyard",
        )

        for _ in range(STEPS_IN_A_TURN):
            _stepped(client, session_id, found)

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

    return found


def _stepped(client: TestClient, session_id: str, found: set[str]) -> dict[str, object]:
    """End a step and collect what the boards it produced carried.

    Three events rather than one: a step ends when every player has passed in
    succession (CR 500.2). The passes go through the same route as everything
    else, so the fields they answer with count towards the contract too -- a
    board sent in reply to a pass is a board the app renders.
    """
    body = stepped(client, session_id)
    found.update(keys(body))
    return body


def _is(card: dict[str, object], name: str) -> bool:
    """Whether this card is the one named."""
    return card.get("name") == name
