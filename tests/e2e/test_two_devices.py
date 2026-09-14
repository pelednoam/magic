"""One game, two views -- and the advice that reaches both of them.

The reason there is a server at all (§4): the phone and the tablet are windows
onto one authoritative game, not two games kept in step.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from snapshot import STEPS_IN_TWO_TURNS, advice, send, start, zone
from wire import decoded, number, obj, rows, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient


def test_a_second_device_hears_about_an_event_it_did_not_send(client: TestClient) -> None:
    session_id = start(client)
    with client.websocket_connect(f"/games/{session_id}/watch") as tablet:
        tablet.receive_json()
        send(client, session_id, type="change_life", player="you", amount=-4)
        update = decoded(tablet.receive_json())
        assert number(update, "state", "players", "you", "life") == 16
        assert number(update, "advice", "you", "life") == 16


def test_the_attack_advisor_over_the_wire(client: TestClient) -> None:
    """Two Savannah Lions against nothing: attack with both, four damage."""
    session_id = start(client)
    body = send(client, session_id, type="advance_step")
    for lion in [c for c in zone(body, "them", "hand") if text(c, "name") == "Savannah Lions"]:
        body = send(
            client,
            session_id,
            type="move_card",
            player="them",
            instance_id=lion["instance_id"],
            to="battlefield",
        )

    for _ in range(STEPS_IN_TWO_TURNS):
        body = send(client, session_id, type="advance_step")
        theirs = text(body, "state", "active_player") == "them"
        if theirs and text(body, "state", "step") == "declare_attackers":
            break

    attacks = obj(advice(body, "them"), "attacks")
    assert text(attacks, "unavailable") == ""
    best = rows(attacks, "plans")[0]
    assert words(best, "attackers") == ["Savannah Lions", "Savannah Lions"]
    assert number(best, "damage") == 4
    assert number(best, "defender_life_after") == 16
