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

from typing import TYPE_CHECKING

from helpers_api import RULES, server, talking
from helpers_fakes import Answering
from mtgcoach.rules.answer import Answer
from wire import flag, obj, rows, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200

GOOD = Answer(
    answer="Lethal damage goes to the blocker first; the rest tramples over.",
    in_short="The extra damage still gets through.",
    citations=("702.19b",),
)


def new_game(client: TestClient) -> str:
    body = client.post("/games", json={"mine": "green", "theirs": "other"}).json()
    session_id: str = body["session_id"]
    return session_id


def ask(client: TestClient, session_id: str, **body: object) -> dict[str, object]:
    response = client.post(
        f"/games/{session_id}/ask",
        json={"question": "how does trample work?", **body},
    )
    assert response.status_code == HTTP_OK, response.text
    answered: dict[str, object] = response.json()
    return answered


def test_an_answer_citing_a_retrieved_rule_is_passed_on() -> None:
    with talking(server(asker=Answering(GOOD), rules=RULES)) as client:
        body = ask(client, new_game(client))
        assert flag(body, "cited")
        assert text(obj(body, "answer"), "in_short") == "The extra damage still gets through."
        assert words(obj(body, "answer"), "citations") == ["702.19b"]


def test_the_rules_it_was_given_come_back_too() -> None:
    """The certainly-true half. A player can read these whatever was said."""
    with talking(server(asker=Answering(GOOD), rules=RULES)) as client:
        found = rows(ask(client, new_game(client)), "rules")
        assert "702.19b" in [text(rule, "reference") for rule in found]
        assert all(text(rule, "text") for rule in found)


def test_an_answer_citing_a_rule_it_was_not_given_is_refused() -> None:
    """The whole point of the layer, exercised through the route."""
    invented = Answer(
        answer="Rule 999.9z says the trample damage is doubled.",
        in_short="It does double damage!",
        citations=("999.9z",),
    )
    with talking(server(asker=Answering(invented), rules=RULES)) as client:
        body = ask(client, new_game(client))
        assert not flag(body, "cited")
        answer = obj(body, "answer")
        assert "double" not in text(answer, "in_short")
        assert "999.9z" in text(answer, "unsure")
        # And the retrieved rules are still there, so the question is not lost.
        assert rows(body, "rules")


def test_an_uncited_answer_is_refused() -> None:
    """Fluent, plausible, and impossible to look up -- the shape of a guess."""
    guessed = Answer(answer="It just works.", in_short="It works.")
    with talking(server(asker=Answering(guessed), rules=RULES)) as client:
        assert not flag(ask(client, new_game(client)), "cited")


def test_saying_it_is_unsure_does_not_excuse_citing_nothing() -> None:
    """The hole this closed: a claim with a disclaimer stapled to it.

    `unsure` used to exempt an answer from citing anything at all, so a
    confident uncited paragraph passed as long as it also admitted to some
    unrelated doubt.
    """
    unsure = Answer(
        answer="Trample doubles all damage.",
        in_short="It does double damage!",
        unsure="one minor detail",
    )
    with talking(server(asker=Answering(unsure), rules=RULES)) as client:
        body = ask(client, new_game(client))
        assert not flag(body, "cited")
        assert "double" not in text(obj(body, "answer"), "in_short")


def test_the_player_defaults_to_you() -> None:
    with talking(server(asker=Answering(GOOD), rules=RULES)) as client:
        assert flag(ask(client, new_game(client)), "cited")


def test_a_question_matching_nothing_is_answered_without_asking() -> None:
    """No rules retrieved means nothing can be cited, so no model is asked.

    The prompt used to tell the model to answer anyway and the checker then
    refused it for having no citations -- so the player got a refusal where the
    truthful answer was "nothing matched", which the server can say itself,
    instantly and for nothing.
    """
    never = Answering(Answer(answer="should not be asked", in_short="x"))
    with talking(server(asker=never, rules=RULES)) as client:
        body = ask(client, new_game(client), question="what is a zzzyzzx?")
        assert not flag(body, "cited")
        assert rows(body, "rules") == []
        assert "Nothing in the Comprehensive Rules matched" in text(obj(body, "answer"), "answer")
        assert "should not be asked" not in text(obj(body, "answer"), "answer")
