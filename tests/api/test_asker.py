"""Reading a rules answer out of the command's output.

The parsing itself lives in ``api.claude`` and is pinned by the explainer
tests; what is here is the answer-shaped part: which fields are taken, and what
counts as no answer at all.
"""

from __future__ import annotations

import json
import subprocess

import pytest

from fakeprocess import Fake
from mtgcoach.api.asker import ClaudeCliAsker, parse
from mtgcoach.coach.advice import ExplainerError
from test_explainer import envelope

ANSWER = {
    "answer": "Lethal damage goes to the blocker first, then the rest tramples over.",
    "in_short": "The extra damage still hurts them.",
    "citations": ["702.19b"],
    "unsure": "",
}


def test_reads_the_agreed_object() -> None:
    got = parse(envelope(json.dumps(ANSWER)))
    assert got.answer.startswith("Lethal damage")
    assert got.in_short == "The extra damage still hurts them."
    assert got.citations == ("702.19b",)
    assert got.unsure == ""


def test_a_malformed_citation_refuses_the_whole_answer() -> None:
    """Dropping one moves the answer towards passing, not away from it.

    The check is "every citation was retrieved". Drop the bad element and what
    is left is all real, so a malformed list becomes a clean bill of health.
    """
    with pytest.raises(ExplainerError, match="'citations' was not a list"):
        parse(envelope(json.dumps({**ANSWER, "citations": ["702.19b", 7]})))


def test_a_citation_list_that_is_not_a_list_refuses_the_answer() -> None:
    with pytest.raises(ExplainerError, match="'citations' was not a list"):
        parse(envelope(json.dumps({**ANSWER, "citations": "702.19b"})))


def test_no_citations_at_all_is_read_and_left_to_the_checker() -> None:
    """Absent is not malformed. `rules.answer` is what refuses an uncited one."""
    got = parse(envelope(json.dumps({"answer": "Maybe.", "in_short": "Maybe."})))
    assert got.citations == ()


def test_an_answer_that_is_only_an_admission_of_doubt_survives() -> None:
    """Saying "these rules do not settle it" is an answer, and a good one."""
    got = parse(envelope(json.dumps({"unsure": "Nothing here covers that."})))
    assert got.unsure == "Nothing here covers that."
    assert got.citations == ()


def test_an_answer_with_nothing_in_it_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="answer was empty"):
        parse(json.dumps({"type": "result", "result": None}))


def test_an_answer_that_is_only_citations_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="answer was empty"):
        parse(envelope(json.dumps({"citations": ["702.19b"]})))


def test_prose_with_no_object_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="did not answer with an object"):
        parse(envelope("I'm sorry, I can't help with that."))


def test_the_briefing_is_what_gets_sent() -> None:
    """The briefing, and only the briefing.

    The question is already inside it, fenced as data. Sending it separately
    would put an unfenced copy in front of the model, which is the hazard the
    fence exists for.
    """
    fake = Fake(stdout=envelope(json.dumps(ANSWER)))
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(subprocess, "Popen", fake)
        got = ClaudeCliAsker().ask("how does trample work?", "the briefing")
    assert got.citations == ("702.19b",)
    assert fake.stdin == "the briefing"
