"""What stands in for the two things this project asks a model.

Split from ``helpers_api`` at the length limit, and the seam is a real one:
that module builds a server out of cards, and these four are what it is built
*with* -- two that answer whatever a test prepared, two that never answer at
all.

The refusing pair is the default everywhere, deliberately: no test can
accidentally spawn a real ``claude``, which would be slow, would cost quota,
and would pass or fail for reasons nothing in this repository controls.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.coach.advice import ExplainerError

if TYPE_CHECKING:
    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.rules.answer import Answer


@dataclass(slots=True)
class Canned:
    """An explainer that says what the test told it to say.

    Mutable, because an instance id only exists once a game has been dealt --
    so a test that recommends a real card has to start the game, read the hand,
    and only then decide what the coach will say about it.
    """

    said: Explanation

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """The prepared answer, whatever was asked."""
        del report, briefing
        return self.said


@dataclass(frozen=True, slots=True)
class NoCoach:
    """An explainer that is never available. The default, deliberately.

    Every test gets this unless it asks for something else, so no test can
    accidentally spawn a real ``claude`` -- which would be slow, would cost
    quota, and would pass or fail for reasons nothing in the repository
    controls.
    """

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """Never answer.

        Raises:
            ExplainerError: Always.
        """
        del report, briefing
        msg = "no coach in this test"
        raise ExplainerError(msg)


@dataclass(slots=True)
class Answering:
    """An answerer that says what the test told it to say."""

    said: Answer

    def ask(self, question: str, briefing: str) -> Answer:
        """The prepared answer, whatever was asked."""
        del question, briefing
        return self.said


@dataclass(frozen=True, slots=True)
class NoAnswers:
    """An answerer that is never available. The default, for the same reason."""

    def ask(self, question: str, briefing: str) -> Answer:
        """Never answer.

        Raises:
            ExplainerError: Always.
        """
        del question, briefing
        msg = "no answerer in this test"
        raise ExplainerError(msg)
