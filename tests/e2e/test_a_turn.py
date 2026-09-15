"""A whole turn, end to end, through everything the real thing uses.

No fakes below the HTTP client. The cards come out of the real Scryfall reader
into the real SQLite store; their behaviour comes out of the real sealed FDN
fixture that a person signed; the rules are the real engine; the advice is the
real coach; and it is all reached over real HTTP.

The unit tests say each piece is right. This says they are the *same* pieces --
that an oracle id written by the extractor is the one the store hands back, and
that a ``{T}: Add {G}`` a model proposed and a human accepted becomes a Forest
the mana solver will tap.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from snapshot import (
    advice,
    board,
    card,
    look,
    refuse,
    send,
    start,
    stepped,
    undo,
    verdicts,
    zone,
)
from wire import flag, number, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

#: Untap, upkeep, draw, then the first main phase.
STEPS_TO_MAIN = 3


def _to_main(client: TestClient, session_id: str) -> dict[str, object]:
    """Walk from the start of the game to the first main phase."""
    body = look(client, session_id)
    for _ in range(STEPS_TO_MAIN):
        body = stepped(client, session_id)
    assert text(body, "state", "step") == "precombat_main"
    return body


def test_the_real_card_data_reaches_the_engine(client: TestClient) -> None:
    """The two halves line up: the store names it, the fixture gives it rules."""
    body = look(client, start(client))
    held = {text(c, "name") for c in zone(body, "you", "hand")}
    assert held == {"Forest", "Llanowar Elves", "Druid of the Cowl", "Giant Growth"}
    assert words(advice(body, "you"), "unknown") == [], "this deck is fully modelled"


def test_playing_the_first_land(client: TestClient) -> None:
    session_id = start(client)
    body = _to_main(client, session_id)

    # One land in hand is playable; a two-mana creature is not, and says why.
    assert flag(verdicts(body, "you")["Forest"], "playable")
    druid = verdicts(body, "you")["Druid of the Cowl"]
    assert not flag(druid, "playable")
    assert "you need 2 more untapped sources" in words(druid, "reasons")

    forest = card(body, "you", "hand", "Forest")
    body = send(
        client, session_id, type="play_land", player="you", instance_id=forest["instance_id"]
    )
    assert card(body, "you", "battlefield", "Forest")
    assert number(board(body, "you"), "lands_played_this_turn") == 1

    # The land drop is spent, so the next Forest is refused -- by name.
    assert "you have already played a land this turn" in words(
        verdicts(body, "you")["Forest"], "reasons"
    )


def test_the_report_says_which_land_to_tap(client: TestClient) -> None:
    """Not "you can cast this" but "cast it with this one"."""
    session_id = start(client)
    body = _to_main(client, session_id)
    forest = card(body, "you", "hand", "Forest")
    body = send(
        client, session_id, type="play_land", player="you", instance_id=forest["instance_id"]
    )
    elves = verdicts(body, "you")["Llanowar Elves"]
    assert flag(elves, "playable")
    assert words(elves, "payment", "tap") == [text(forest, "instance_id")]
    assert words(elves, "payment", "keep") == []


def test_a_creature_cannot_be_played_as_a_land(client: TestClient) -> None:
    """CR 305.1, checked here because `core` has no card data to check it with."""
    session_id = start(client)
    body = _to_main(client, session_id)
    druid = card(body, "you", "hand", "Druid of the Cowl")
    reason = refuse(
        client, session_id, type="play_land", player="you", instance_id=druid["instance_id"]
    )
    assert "Druid of the Cowl is not a land" in reason


def test_a_summoning_sick_creature_makes_no_mana(client: TestClient) -> None:
    """CR 302.6, through the whole stack: Elves do nothing the turn they land.

    The rule is in ``core``, the ``{T}: Add {G}`` is in the sealed fixture, and
    the sickness is in the session's state. This is the only test that puts all
    three together.
    """
    session_id = start(client)
    body = _to_main(client, session_id)
    elves = card(body, "you", "hand", "Llanowar Elves")
    body = send(
        client,
        session_id,
        type="move_card",
        player="you",
        instance_id=elves["instance_id"],
        to="battlefield",
    )
    assert flag(card(body, "you", "battlefield", "Llanowar Elves"), "summoning_sick")

    growth = verdicts(body, "you")["Giant Growth"]
    assert not flag(growth, "playable")
    assert "you need 1 more untapped source" in words(growth, "reasons")


def test_undo_puts_the_land_back(client: TestClient) -> None:
    session_id = start(client)
    body = _to_main(client, session_id)
    forest = card(body, "you", "hand", "Forest")
    send(client, session_id, type="play_land", player="you", instance_id=forest["instance_id"])

    undone = undo(client, session_id)
    assert number(board(undone, "you"), "lands_played_this_turn") == 0
    assert zone(undone, "you", "battlefield") == []
    assert card(undone, "you", "hand", "Forest")
