# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app: the TestClient's response type is opaque to strict
# pyright, and everything read out of it here is narrowed by ``wire``.

"""What the rules question route refuses, and why.

This route has no auth in front of it, spends the operator's quota, and holds a
Node process for up to a minute. The rest of the server is instant and free, so
none of these limits exist anywhere else -- they are all about this one, and
they read better together than scattered among the tests about answers.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING

from fastapi.testclient import TestClient

from helpers_api import RULES, Answering, server
from mtgcoach.api import rationing
from test_app_ask import GOOD, ask, new_game

if TYPE_CHECKING:
    from mtgcoach.rules.answer import Answer

HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNAVAILABLE = 503


def test_an_empty_question_is_a_bad_request() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(f"/games/{new_game(client)}/ask", json={"question": "   "})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "ask a question" in response.json()["detail"]


def test_a_missing_question_is_a_bad_request() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(f"/games/{new_game(client)}/ask", json={})
        assert response.status_code == HTTP_BAD_REQUEST


def test_a_game_that_is_not_there_is_a_404_before_anything_else() -> None:
    """Even with no question and no rules installed: the game comes first."""
    with TestClient(server()) as client:
        response = client.post("/games/nope/ask", json={})
        assert response.status_code == HTTP_NOT_FOUND


def test_a_player_who_is_not_in_the_game_is_a_bad_request() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(
            f"/games/{new_game(client)}/ask",
            json={"question": "anything", "player": "nobody"},
        )
        assert response.status_code == HTTP_BAD_REQUEST


def test_a_server_without_the_rules_installed_says_so() -> None:
    """A legitimate way to run this. The tracker and the turn coach still work."""
    with TestClient(server(asker=Answering(GOOD))) as client:
        response = client.post(f"/games/{new_game(client)}/ask", json={"question": "trample?"})
        assert response.status_code == HTTP_UNAVAILABLE
        assert "Comprehensive Rules are not installed" in response.json()["detail"]


def test_no_answerer_is_a_503() -> None:
    with TestClient(server(rules=RULES)) as client:
        response = client.post(f"/games/{new_game(client)}/ask", json={"question": "trample?"})
        assert response.status_code == HTTP_UNAVAILABLE
        assert "no answerer in this test" in response.json()["detail"]


def test_asking_does_not_change_the_game() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        session_id = new_game(client)
        before = client.get(f"/games/{session_id}").json()
        ask(client, session_id)
        assert client.get(f"/games/{session_id}").json() == before


def test_a_very_long_question_is_refused_before_it_reaches_anything() -> None:
    """It goes into an FTS5 expression and into a prompt, so it has a length.

    Past a sentence or two it is either a mistake or somebody filling the
    prompt with their own text, and both are answered better by saying so.
    """
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(
            f"/games/{new_game(client)}/ask",
            json={"question": "trample? " * 200},
        )
        assert response.status_code == HTTP_BAD_REQUEST
        assert "keep it under" in response.json()["detail"]


def test_only_so_many_questions_run_at_once() -> None:
    """No auth, and each of these holds a Node process for up to a minute.

    Not a security boundary -- nothing here is -- but it turns "unbounded
    subprocesses" into "a queue", which is the difference between a slow
    tracker and a laptop somebody has to reboot.
    """
    started = threading.Barrier(rationing.MAX_IN_FLIGHT + 1, timeout=5)
    release = threading.Event()

    @dataclass(frozen=True, slots=True)
    class Slow:
        """An answerer that blocks until the test lets it go."""

        def ask(self, question: str, briefing: str) -> Answer:
            """Wait, then answer."""
            del question, briefing
            started.wait()
            release.wait(timeout=5)
            return GOOD

    with TestClient(server(asker=Slow(), rules=RULES)) as client:
        session_id = new_game(client)
        holding = [
            threading.Thread(target=lambda: ask(client, session_id))
            for _ in range(rationing.MAX_IN_FLIGHT)
        ]
        for worker in holding:
            worker.start()
        try:
            started.wait()
            refused = client.post(
                f"/games/{session_id}/ask",
                json={"question": "one more"},
            )
            assert refused.status_code == HTTP_UNAVAILABLE
            assert "busy" in refused.json()["detail"]
        finally:
            release.set()
            for worker in holding:
                worker.join(timeout=5)


def test_only_so_many_questions_in_a_minute() -> None:
    """The failure that needs no attacker: a stuck finger, or a reload loop.

    Both routes start a `claude` process and spend the operator's
    subscription, and the client calling them is a phone with a button on it.
    The concurrency cap bounds how many run at once; this bounds how many run
    at all.
    """
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        session_id = new_game(client)
        for _ in range(rationing.BURST):
            ask(client, session_id)
        refused = client.post(f"/games/{session_id}/ask", json={"question": "one more"})
        assert refused.status_code == HTTP_UNAVAILABLE
        assert "a lot of questions" in refused.json()["detail"]


def test_a_refused_busy_request_does_not_spend_a_token() -> None:
    """A refusal is not a request.

    A player retrying two seconds later should not be paying for the attempt
    that never started.
    """
    rations = rationing.Rationed()
    held = [rations.take() for _ in range(rationing.MAX_IN_FLIGHT)]
    assert held == [""] * rationing.MAX_IN_FLIGHT

    assert "busy" in rations.take(), "the concurrency cap, not the rate limit"
    for _ in held:
        rations.release()

    # Only the ones that actually ran were charged, so the rest of the minute's
    # allowance is still there.
    for _ in range(rationing.BURST - rationing.MAX_IN_FLIGHT):
        assert rations.take() == ""
        rations.release()
    assert "a lot of questions" in rations.take()


def test_tokens_come_back_over_time() -> None:
    """Otherwise a long game would run out halfway through."""
    rations = rationing.Rationed(burst=2, window=0.05)
    assert rations.take() == ""
    rations.release()
    assert rations.take() == ""
    rations.release()
    assert "a lot of questions" in rations.take()
    time.sleep(0.08)
    assert rations.take() == ""
