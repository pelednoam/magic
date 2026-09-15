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
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from wire import decoded, rows, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

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
    """Send one event, insisting it was accepted, and hand back the board."""
    sent = client.post(f"/games/{session_id}/events", json=event)
    assert sent.status_code == HTTP_OK, sent.text
    return decoded(sent.json())
