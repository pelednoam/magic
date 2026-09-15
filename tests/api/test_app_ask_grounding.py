# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Same reason as test_app_ask: the TestClient's response type is opaque to
# strict pyright, and everything read out of it here is narrowed by ``wire``.

"""R07 through the route, which is the only path an answer can take.

``test_answer`` and ``test_grounding`` check the pieces. These check the wiring,
because every part of this finding is a wiring failure: the card database had
Dazzling Angel's text all along and the prompt never carried it, and the
grounding check is worth nothing unless the route hands it the evidence and the
document's keyword names. A default argument that nobody passes is a check that
does not run, and the only thing that can catch that is a test of the caller.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.api.position import Position

from helpers import ME
from helpers_api import CATALOGUE, RULES, server, talking
from helpers_coach import game
from helpers_fakes import Answering
from mtgcoach.api.asking import answered
from mtgcoach.coach.report import advise
from mtgcoach.rules.answer import Answer
from wire import decoded, flag, obj, rows, text, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

HTTP_OK = 200

#: Cites a retrieved rule, says something no retrieved rule says. R07's probe,
#: in the shape the route sees it.
UNGROUNDED = Answer(
    answer="Trample doubles all damage to the blocker and the player.",
    in_short="Your creature hits twice as hard.",
    citations=("702.19b",),
)

#: Cites a retrieved rule and explains an ability nothing retrieved mentions.
#: Only refusable if the route passes the document's keyword names through.
DRIFTED = Answer(
    answer="Your creature has deathtouch, so any damage at all is lethal.",
    in_short="One point is enough.",
    citations=("702.19b",),
)

GOOD = Answer(
    answer="Assign lethal damage to each blocker first; the rest goes to the player.",
    in_short="The extra damage still gets through.",
    citations=("702.19b",),
)


@dataclass(slots=True)
class Recording:
    """An answerer that keeps the prompt it was given.

    The only way to assert what was *sent*. Half of R07 is that a fact the
    server held never reached the prompt, and no assertion about the reply can
    see that.
    """

    said: Answer
    briefings: list[str] = field(default_factory=list[str])

    def ask(self, question: str, briefing: str) -> Answer:
        """Keep the prompt, then answer as told."""
        del question
        self.briefings.append(briefing)
        return self.said


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


def test_the_prompt_the_route_builds_carries_the_card_text() -> None:
    """Half (a), through the route rather than through ``brief`` directly.

    The opening hand holds a Giant Growth, so there is a card with real text in
    the position before anybody plays anything.
    """
    asker = Recording(GOOD)
    with talking(server(asker=asker, rules=RULES)) as client:
        ask(client, new_game(client))
    (briefing,) = asker.briefings
    assert "WHAT THESE CARDS SAY" in briefing
    assert "Target creature gets +3/+3 until end of turn." in briefing


def test_an_ungrounded_answer_is_refused_and_says_which_check_objected() -> None:
    """Half (b). The claim is not shown, and the two verdicts differ.

    `cited` passes -- 702.19b was retrieved -- and `grounded` does not, which is
    the whole reason they are two booleans: a refusal that could not say which
    happened would leave a parent unable to tell "it quoted a rule nobody gave
    it" from "it said something no rule says".
    """
    with talking(server(asker=Answering(UNGROUNDED), rules=RULES)) as client:
        body = ask(client, new_game(client))
        assert flag(body, "cited")
        assert not flag(body, "grounded")
        answer = obj(body, "answer")
        assert "twice as hard" not in text(answer, "in_short")
        assert "doubled" in text(answer, "unsure")
        # And the retrieved rules are still there, so the question is not lost.
        assert rows(body, "rules")


def test_the_route_passes_the_documents_keyword_names_to_the_check() -> None:
    """Otherwise the ability half of the grounding check silently does nothing.

    ``Given.keywords`` defaults to empty, because a list of keywords written in
    Python would be wrong by the next set -- so the names have to come off the
    index, and this is the test that they do.
    """
    with talking(server(asker=Answering(DRIFTED), rules=RULES)) as client:
        body = ask(client, new_game(client))
        assert not flag(body, "grounded")
        assert "deathtouch" in text(obj(body, "answer"), "unsure")


def test_a_grounded_answer_comes_back_with_both_verdicts_true() -> None:
    with talking(server(asker=Answering(GOOD), rules=RULES)) as client:
        body = ask(client, new_game(client))
        assert flag(body, "cited")
        assert flag(body, "grounded")
        assert words(obj(body, "answer"), "citations") == ["702.19b"]


def test_every_reply_says_what_was_not_checked() -> None:
    """The gap, in the server's words, so nothing can be mistaken for a proof.

    On the answer that passed both checks especially: that is the reply a parent
    is most likely to act on, and neither boolean means the answer is right.
    """
    with talking(server(asker=Answering(GOOD), rules=RULES)) as client:
        said = words(ask(client, new_game(client)), "unchecked")
    assert said
    assert "read the cited rules" in said[0]


def test_a_question_matching_nothing_also_says_what_was_not_checked() -> None:
    """And is not reported as ungrounded, which would be alarming and wrong.

    There were no claims and nothing to ground them in. "This answer went
    beyond its evidence" over the sentence "I could not find a rule about that"
    is the same mistake `matched` was added to fix for `cited`.
    """
    never = Answering(Answer(answer="should not be asked", in_short="x"))
    with talking(server(asker=never, rules=RULES)) as client:
        body = ask(client, new_game(client), question="what is a zzzyzzx?")
        assert not flag(body, "matched")
        assert flag(body, "grounded")
        assert words(body, "unchecked")


def test_a_position_with_no_board_grounds_against_the_rules_alone() -> None:
    """Not a position this route builds, and it must not claim more if it were.

    ``answered`` is reached through ``position(board=True)``, so the card text
    is always there in the server. A caller that asked without a board gets a
    check against the retrieved passages only -- less checking, not a claim
    that nothing needed checking -- and the probe is still refused, because its
    arithmetic was never in any rule.
    """
    state = game(hand=("Growth",))
    position = Position(report=advise(state, ME, CATALOGUE), revision=0)
    body = decoded(answered(Answering(UNGROUNDED), RULES, "how does trample work?", position))
    assert not flag(body, "grounded")
