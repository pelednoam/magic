# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app: the TestClient's response type is opaque to strict
# pyright, and everything read out of it here is narrowed by ``wire``.

"""The rules question route, with the model's answer written here.

The route's job is to be the one path an answer can take, so the citation check
cannot be gone round. These are about that: an answer citing a rule it was
given arrives, one citing a rule it invented is replaced, and the passages that
were retrieved come back either way -- those are the part that is certainly
true, and a player can read them whatever the model said.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from helpers_api import RULES, Answering, server
from mtgcoach.rules.answer import Answer
from wire import flag, obj, rows, text, words

HTTP_OK = 200
HTTP_BAD_REQUEST = 400
HTTP_NOT_FOUND = 404
HTTP_UNAVAILABLE = 503

GOOD = Answer(
    answer="Lethal damage goes to the blocker first; the rest tramples over.",
    in_short="The extra damage still gets through.",
    citations=("702.19b",),
)


def _game(client: TestClient) -> str:
    body = client.post("/games", json={"you": "green", "them": "other"}).json()
    session_id: str = body["session_id"]
    return session_id


def _ask(client: TestClient, session_id: str, **body: object) -> dict[str, object]:
    response = client.post(
        f"/games/{session_id}/ask",
        json={"question": "how does trample work?", **body},
    )
    assert response.status_code == HTTP_OK, response.text
    answered: dict[str, object] = response.json()
    return answered


def test_an_answer_citing_a_retrieved_rule_is_passed_on() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        body = _ask(client, _game(client))
        assert flag(body, "trusted")
        assert text(obj(body, "answer"), "in_short") == "The extra damage still gets through."
        assert words(obj(body, "answer"), "citations") == ["702.19b"]


def test_the_rules_it_was_given_come_back_too() -> None:
    """The certainly-true half. A player can read these whatever was said."""
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        found = rows(_ask(client, _game(client)), "rules")
        assert "702.19b" in [text(rule, "reference") for rule in found]
        assert all(text(rule, "text") for rule in found)


def test_an_answer_citing_a_rule_it_was_not_given_is_refused() -> None:
    """The whole point of the layer, exercised through the route."""
    invented = Answer(
        answer="Rule 999.9z says the trample damage is doubled.",
        in_short="It does double damage!",
        citations=("999.9z",),
    )
    with TestClient(server(asker=Answering(invented), rules=RULES)) as client:
        body = _ask(client, _game(client))
        assert not flag(body, "trusted")
        answer = obj(body, "answer")
        assert "double" not in text(answer, "in_short")
        assert "999.9z" in text(answer, "unsure")
        # And the retrieved rules are still there, so the question is not lost.
        assert rows(body, "rules")


def test_an_uncited_answer_is_refused() -> None:
    """Fluent, plausible, and impossible to look up -- the shape of a guess."""
    guessed = Answer(answer="It just works.", in_short="It works.")
    with TestClient(server(asker=Answering(guessed), rules=RULES)) as client:
        assert not flag(_ask(client, _game(client)), "trusted")


def test_an_answer_that_says_it_is_unsure_may_cite_nothing() -> None:
    unsure = Answer(
        answer="These rules do not cover that.",
        in_short="I am not sure — let us read the card.",
        unsure="Nothing retrieved covers this.",
    )
    with TestClient(server(asker=Answering(unsure), rules=RULES)) as client:
        assert flag(_ask(client, _game(client)), "trusted")


def test_a_question_matching_no_rule_is_still_answered() -> None:
    """With a prompt that says there is nothing to cite, not a hidden box."""
    unsure = Answer(in_short="Nothing in the rules covers that.", unsure="no match")
    with TestClient(server(asker=Answering(unsure), rules=RULES)) as client:
        body = _ask(client, _game(client), question="what is a zzzyzzx?")
        assert flag(body, "trusted")
        assert rows(body, "rules") == []


def test_an_empty_question_is_a_bad_request() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(f"/games/{_game(client)}/ask", json={"question": "   "})
        assert response.status_code == HTTP_BAD_REQUEST
        assert "ask a question" in response.json()["detail"]


def test_a_missing_question_is_a_bad_request() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(f"/games/{_game(client)}/ask", json={})
        assert response.status_code == HTTP_BAD_REQUEST


def test_a_game_that_is_not_there_is_a_404_before_anything_else() -> None:
    """Even with no question and no rules installed: the game comes first."""
    with TestClient(server()) as client:
        response = client.post("/games/nope/ask", json={})
        assert response.status_code == HTTP_NOT_FOUND


def test_a_player_who_is_not_in_the_game_is_a_bad_request() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        response = client.post(
            f"/games/{_game(client)}/ask",
            json={"question": "anything", "player": "nobody"},
        )
        assert response.status_code == HTTP_BAD_REQUEST


def test_the_player_defaults_to_you() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        assert flag(_ask(client, _game(client)), "trusted")


def test_a_server_without_the_rules_installed_says_so() -> None:
    """A legitimate way to run this. The tracker and the turn coach still work."""
    with TestClient(server(asker=Answering(GOOD))) as client:
        response = client.post(f"/games/{_game(client)}/ask", json={"question": "trample?"})
        assert response.status_code == HTTP_UNAVAILABLE
        assert "Comprehensive Rules are not installed" in response.json()["detail"]


def test_no_answerer_is_a_503() -> None:
    with TestClient(server(rules=RULES)) as client:
        response = client.post(f"/games/{_game(client)}/ask", json={"question": "trample?"})
        assert response.status_code == HTTP_UNAVAILABLE
        assert "no answerer in this test" in response.json()["detail"]


def test_asking_does_not_change_the_game() -> None:
    with TestClient(server(asker=Answering(GOOD), rules=RULES)) as client:
        session_id = _game(client)
        before = client.get(f"/games/{session_id}").json()
        _ask(client, session_id)
        assert client.get(f"/games/{session_id}").json() == before
