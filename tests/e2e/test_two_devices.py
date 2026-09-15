"""One game, two views -- and the advice that reaches each of them.

The reason there is a server at all (§4): the phone and the tablet are windows
onto one authoritative game, not two games kept in step.

Two *different* windows, since seats got their own tokens: each is sent its own
hand and its own advice, so a test about the other player's attack has to ask
the other player's device. Reading both off one board is what this project
stopped doing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import THEIRS
from snapshot import STEPS_IN_TWO_TURNS, advice, look, send, start, stepped, zone
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
    stepped(client, session_id)
    # Their hand, from their device: this one is not sent it (CR 400.2).
    body = look(client, session_id, THEIRS)
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
        body = stepped(client, session_id)
        theirs = text(body, "state", "active_player") == "them"
        if theirs and text(body, "state", "step") == "declare_attackers":
            break

    # And their advice from their device, for the same reason: a turn report
    # names every card in the hand it is about.
    attacks = obj(advice(look(client, session_id, THEIRS), "them"), "attacks")
    assert text(attacks, "unavailable") == ""
    best = rows(attacks, "plans")[0]
    assert words(best, "attackers") == ["Savannah Lions", "Savannah Lions"]
    assert number(best, "damage") == 4
    assert number(best, "defender_life_after") == 16
