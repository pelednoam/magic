"""Asking Claude a rules question, with the rules already in the prompt.

The retrieval happens before this: whoever calls ``ask`` has already searched
the Comprehensive Rules and built a briefing that quotes what it found. So the
model is not being asked what the rules are. It is being handed them and asked
what they mean for this board, in words a child can use.

``rules.answer.verify`` then checks that every rule it cited was one of the
ones supplied -- which is the difference between an answer somebody can look up
and an answer that merely sounds like one.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from mtgcoach.api.claude import Cli, object_in, text, words
from mtgcoach.coach.advice import ExplainerError
from mtgcoach.rules.answer import Answer


@dataclass(frozen=True, slots=True)
class ClaudeCliAsker:
    """An answerer backed by the local ``claude`` command."""

    cli: Cli = field(default_factory=Cli)

    def ask(self, question: str, briefing: str) -> Answer:
        """Answer a rules question.

        Raises:
            ExplainerError: If the command fails, times out, or answers with
                something that is not the agreed object.
        """
        del question  # it is already in the briefing, fenced as data
        return parse(self.cli.run(briefing))


def parse(stdout: str) -> Answer:
    """Turn the command's output into an answer.

    Raises:
        ExplainerError: If there is no usable answer in there.
    """
    payload = object_in(stdout)
    answer = Answer(
        answer=text(payload, "answer"),
        in_short=text(payload, "in_short"),
        citations=words(payload, "citations"),
        unsure=text(payload, "unsure"),
    )
    if not answer.answer and not answer.in_short and not answer.unsure:
        # The CLI's error envelope decodes to a well-formed object with none of
        # these in it. An empty answer shown as an answer looks like the rules
        # had nothing to say about the question, which is never true.
        msg = "the coach's answer was empty"
        raise ExplainerError(msg)
    return answer
