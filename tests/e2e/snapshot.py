"""Driving the server from both devices, and reading what each is told.

Two clients, one per seat, because a token names a seat: an event may only name
the player whose token sent it, and a board carries one hand -- its own. So a
helper that sends an event reaches for the device that seat holds, and a helper
that reads the other player's cards asks *their* device. See ``test_seats`` in
``tests/api``, which is where the refusals themselves are tested.
"""

# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined to this module on purpose:
# everything it returns is narrowed by ``wire``, so no test past here works with
# an unknown type.

from __future__ import annotations

from fastapi.testclient import TestClient

from helpers_api import MINE, SEATING
from wire import by_name, decoded, named, obj, rows, text, words

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_UNAVAILABLE = 503

#: Enough advances to reach the other player's combat from anywhere.
STEPS_IN_TWO_TURNS = 24


def start(client: TestClient) -> str:
    """Begin a game and return its name.

    The decks are named from the posting device's side; the server deals
    "mine" to the seat its token holds.
    """
    response = client.post("/games", json={"mine": "green", "theirs": "white"})
    assert response.status_code == HTTP_OK, response.text
    return text(decoded(response.json()), "session_id")


def device(client: TestClient, seat: str) -> TestClient:
    """The same server, spoken to by the device that holds ``seat``'s token.

    The same *app*, which is what makes it the same game: a second client on a
    second app would be a second server with its own store, and every event
    would land in a game the first has never heard of.
    """
    if seat == MINE:
        return client
    return TestClient(client.app, headers={"Authorization": f"Bearer {SEATING.token(seat)}"})


def send(client: TestClient, session_id: str, **event: object) -> dict[str, object]:
    """Send one event, from the device that holds the seat it names.

    ``advance_step`` names nobody -- ending a step is a consequence of every
    player passing (CR 117.4), not a move -- and goes from whichever device the
    test is holding.
    """
    who = event.get("player")
    sender = device(client, who) if isinstance(who, str) else client
    response = sender.post(f"/games/{session_id}/events", json=event)
    assert response.status_code == HTTP_OK, response.text
    return decoded(response.json())


def stepped(client: TestClient, session_id: str) -> dict[str, object]:
    """End the current step the way CR 500.2 ends it, and enter the next.

    Everybody passes first. Every walk in these tests used to be a bare
    ``advance_step`` and the server used to accept one, which is the half of
    CR 500.2 the rule itself warns against: a step does not end because the
    stack happens to be empty, it ends because each player has had the chance
    to add something to it and declined.

    Who still has to pass comes from the board the server just sent, in the
    order it sent them -- no test works it out for itself, because working it
    out is the engine's job.
    """
    body = look(client, session_id)
    for seat in words(body, "state", "yet_to_pass"):
        send(client, session_id, type="pass_priority", player=seat)
    return send(client, session_id, type="advance_step")


def look(client: TestClient, session_id: str, seat: str = MINE) -> dict[str, object]:
    """The snapshot as it stands, as one seat is sent it.

    ``seat`` because the two are different payloads: each carries its own hand
    and its own advice, and the other player's hand is not in either.
    """
    response = device(client, seat).get(f"/games/{session_id}")
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
    """Take back the last event and return the snapshot it left.

    From whichever device is holding it. Either seat may undo: it is what the
    two of them do when they agree something was recorded wrong, which is the
    tracker catching up with a table rather than a move in the game.
    """
    response = client.post(f"/games/{session_id}/undo")
    assert response.status_code == HTTP_OK, response.text
    return decoded(response.json())


def refuse(client: TestClient, session_id: str, **event: object) -> str:
    """Send an event the server should reject, and return the reason it gave.

    From the seat that names itself, like ``send``: a refusal that came back
    because the *token* was wrong would pass this whatever the rules say.
    """
    who = event.get("player")
    sender = device(client, who) if isinstance(who, str) else client
    response = sender.post(f"/games/{session_id}/events", json=event)
    assert response.status_code == HTTP_BAD_REQUEST, response.text
    return text(decoded(response.json()), "detail")


def ask(
    client: TestClient, session_id: str, player: str = "you", question: str = ""
) -> dict[str, object]:
    """Ask the coach about a player's turn, or about the rules.

    One helper for both because they are the same request shape and the same
    failure modes; the question is what picks the route.
    """
    route = "ask" if question else "coach"
    body = {"player": player, "question": question} if question else {"player": player}
    response = device(client, player).post(f"/games/{session_id}/{route}", json=body)
    assert response.status_code == HTTP_OK, response.text
    return decoded(response.json())


def no_coach(client: TestClient, session_id: str) -> None:
    """Ask the coach and require that it was not available."""
    response = client.post(f"/games/{session_id}/coach", json={"player": "you"})
    assert response.status_code == HTTP_UNAVAILABLE, response.text
