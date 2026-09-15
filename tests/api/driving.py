# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient and httpx's Response are typed loosely enough that
# strict pyright cannot see through them. Confined here, like every other
# module that drives a real client.

"""Driving a test server: walking its steps, and insisting on the answers.

Split from ``helpers_api`` at the length limit, and the seam is a real one --
that module says what a test *server* is made of, this one says how a test
drives it. ``tests/e2e/snapshot.py`` is the same idea for the real thing.

It exists at all because of one rule. A step in which players receive priority
ends when the stack is empty and every player has passed in succession
(CR 500.2), so ending one is three events rather than a request, and a helper
is the only way that stays readable in fifty tests.

It drives the *table*, not a device, which since seats got their own tokens
means it drives two clients. A test hands it one and it reaches for the other
seat's when an event says that seat sent it -- because the server now refuses
an event naming a player other than the token's (see ``test_seats``). The
refusal itself is tested there, against a client built by hand; nothing here
would notice it, which is exactly why it is tested somewhere else.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from helpers_api import MINE, SEATING
from wire import decoded, rows, text, words

#: What an accepted event answers with, and what a refused one does.
HTTP_OK = 200
HTTP_REFUSED = 400


def started(client: TestClient, you: str = "green", them: str = "other") -> str:
    """Begin a game and hand back what it is called."""
    created = decoded(client.post("/games", json={"you": you, "them": them}).json())
    session = created["session_id"]
    assert isinstance(session, str)
    return session


def sent(client: TestClient, session_id: str, event: dict[str, object]) -> dict[str, object]:
    """Apply one event, insisting it was accepted, and hand back the board."""
    return _applied(client, session_id, event)


def forests(body: dict[str, object], seat: str = "you") -> list[dict[str, object]]:
    """Every Forest in one seat's hand. Both fixture decks are green."""
    hand = rows(body, "state", "players", seat, "hand")
    return [card for card in hand if card["name"] == "Forest"]


def stepped(client: TestClient, session_id: str) -> dict[str, object]:
    """End the current step the way CR 500.2 ends it, and enter the next.

    Everybody passes first. Every walk in these tests used to be a bare
    ``advance_step`` and the server used to accept one -- which is the half of
    CR 500.2 the rule itself warns against: a step does not end because the
    stack happens to be empty, it ends because each player has had the chance
    to add something to it and declined.

    Who still has to pass comes off the board the server just sent, in the
    order it sent them. No test works it out for itself, because working it
    out is the engine's job and a client that did it would be a second rules
    engine.
    """
    body = decoded(client.get(f"/games/{session_id}").json())
    for seat in words(body, "state", "yet_to_pass"):
        _applied(client, session_id, {"type": "pass_priority", "player": seat})
    return _applied(client, session_id, {"type": "advance_step"})


def walked(client: TestClient, session_id: str, to: str) -> dict[str, object]:
    """Walk a fresh game forward until it is at step ``to``."""
    body = decoded(client.get(f"/games/{session_id}").json())
    while text(body, "state", "step") != to:
        body = stepped(client, session_id)
    return body


def _applied(client: TestClient, session_id: str, event: dict[str, object]) -> dict[str, object]:
    """Send one event, insisting it was accepted, and hand back the board.

    From the device that holds the seat the event names. ``advance_step`` names
    nobody -- ending a step is not a player's action (CR 117.4) -- and goes
    from whichever device the test was already holding.
    """
    who = event.get("player")
    sender = device(client, who) if isinstance(who, str) else client
    sent = sender.post(f"/games/{session_id}/events", json=event)
    assert sent.status_code == HTTP_OK, sent.text
    return decoded(sent.json())


def device(client: TestClient, seat: str) -> TestClient:
    """The same server, spoken to by the device that holds ``seat``'s token.

    Public, because a test that reads the *other* seat's hand or advice has to
    ask from that seat's device -- the board this one is sent does not carry
    them, which is the point of ``test_seats``.

    The same *app*, which is what makes it the same game: a second client on a
    second app would be a second server with a second store and every event
    would land in a game the first one has never heard of.

    Built on demand rather than threaded through fifty call sites. Not entered
    as a context manager either, which is only needed for lifespan and sockets
    -- this sends requests, and the app it sends them to is already running.
    """
    if seat == MINE:
        return client
    return TestClient(client.app, headers={"Authorization": f"Bearer {SEATING.token(seat)}"})
