"""Answering a rules question: retrieve, ask, check, hand over.

The one path a rules answer can reach a client through, so the citation check
cannot be gone round. The order is the whole design:

1. **Search first.** The question goes to the Comprehensive Rules index before
   it goes to a model, so the passages are chosen by the question rather than
   by what a model felt like quoting.
2. **Quote verbatim.** Those passages go into the prompt as text.
3. **Check afterwards.** Every reference the answer cites must be one of the
   ones supplied, compared exactly.

A question that matches nothing is still asked, and still answered -- with a
prompt that says there is nothing to cite, which is a thing the model is told
to say out loud rather than a reason to hide the box.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.rules.answer import refusal, settle
from mtgcoach.rules.question import ask as briefing_for

if TYPE_CHECKING:
    from mtgcoach.api.views import Json
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.rules.answer import Answer, Asker
    from mtgcoach.rules.search import RuleIndex


def answered(
    asker: Asker,
    index: RuleIndex,
    question: str,
    report: TurnReport,
) -> dict[str, Json]:
    """One question's answer, marked with whether it stayed inside the rules given.

    Raises:
        ExplainerError: If no answer could be got at all.
    """
    passages = index.search(question)
    said, problems = settle(asker.ask(question, briefing_for(question, passages, report)), passages)
    return {
        "answer": _answer(refusal(problems) if problems else said),
        "trusted": not problems,
        # The passages it was given, whether or not it cited them. The player
        # can then read the rule themselves, which is the point of retrieving
        # it -- and is the part of the answer that is certainly true.
        "rules": [{"reference": p.reference, "title": p.title, "text": p.text} for p in passages],
    }


def _answer(said: Answer) -> dict[str, Json]:
    """One answer, on the wire."""
    return {
        "answer": said.answer,
        "in_short": said.in_short,
        "citations": list(said.citations),
        "unsure": said.unsure,
    }
