# mypy: disable-error-code="no-any-return"
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""A game that has ended, over HTTP.

The reproduction from the review, as a test: change a player's life to zero,
advance one step, and the game is over. It used to advance happily, offer the
loser cards to play, and take advice for them -- because nothing in the state
recorded a result, and the only life check in the project lived in the self-play
harness, outside the engine the live path uses.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_api import server, talking
from mtgcoach.core.player import STARTING_LIFE
from wire import decoded, rows, text

if TYPE_CHECKING:
    from fastapi.testclient import TestClient
    from httpx import Response

HTTP_OK = 200
HTTP_REFUSED = 400


def _game(client: TestClient) -> str:
    created = decoded(client.post("/games", json={"you": "green", "them": "other"}).json())
    session = created["session_id"]
    assert isinstance(session, str)
    return session


def _send(client: TestClient, session: str, event: dict[str, object]) -> Response:
    """Apply one event, whatever the server makes of it."""
    return client.post(f"/games/{session}/events", json=event)


def _emptied(client: TestClient, session: str, seat: str = "you") -> dict[str, object]:
    """That seat at zero life, and one step taken so CR 704.5a is checked."""
    drained = _send(
        client, session, {"type": "change_life", "player": seat, "amount": -STARTING_LIFE}
    )
    assert drained.status_code == HTTP_OK, drained.text
    stepped = _send(client, session, {"type": "advance_step"})
    assert stepped.status_code == HTTP_OK, stepped.text
    return decoded(stepped.json())


def test_zero_life_ends_the_game_through_the_live_path() -> None:
    """CR 704.5a, checked at the priority boundary rather than immediately."""
    with talking(server()) as client:
        session = _game(client)
        body = _emptied(client, session)
        assert text(body, "state", "over", "winner") == "them"
        assert [one["player"] for one in rows(body, "state", "over", "lost")] == ["you"]
        assert [one["why"] for one in rows(body, "state", "over", "lost")] == ["life"]


def test_a_finished_game_accepts_nothing_more() -> None:
    """It used to accept everything: steps, draws, plays, advice.

    A tracker that lets a game continue past its result is teaching that the
    game continues past its result.
    """
    with talking(server()) as client:
        session = _game(client)
        _emptied(client, session)
        # All from this device's own seat: an event for the other one is
        # refused before the engine is asked anything (403, `test_seats`), so
        # it would pass this test without the game having ended at all.
        anything: tuple[dict[str, object], ...] = (
            {"type": "advance_step"},
            {"type": "draw_card", "player": "you"},
            {"type": "change_life", "player": "you", "amount": -1},
        )
        for event in anything:
            refused = _send(client, session, event)
            assert refused.status_code == HTTP_REFUSED, event
            assert "the game is over" in refused.text


def test_the_step_does_not_move_when_the_game_ends() -> None:
    """There is nothing to advance to."""
    with talking(server()) as client:
        session = _game(client)
        before = decoded(client.get(f"/games/{session}").json())
        after = _emptied(client, session)
        assert text(after, "state", "step") == text(before, "state", "step")


def test_a_live_game_says_it_is_not_over() -> None:
    """Null rather than absent, so the client has one thing to check."""
    with talking(server()) as client:
        body = decoded(client.get(f"/games/{_game(client)}").json())
        assert body["state"] is not None
        state = body["state"]
        assert isinstance(state, dict)
        assert state["over"] is None
