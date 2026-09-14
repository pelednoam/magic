"""Asking Claude what to do about a turn.

The prompt comes from the engine's report and the answer goes straight to
``advice.verify``, which decides whether any of it may be shown. This module
only turns one into the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.api.claude import Cli, object_in, text, words
from mtgcoach.coach.advice import ExplainerError, Explanation

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.coach.report import TurnReport


@dataclass(frozen=True, slots=True)
class ClaudeCliExplainer:
    """An explainer backed by the local ``claude`` command."""

    cli: Cli = field(default_factory=Cli)

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """Advise on this turn.

        Raises:
            ExplainerError: If the command fails, times out, or answers with
                something that is not the agreed object.
        """
        idle = _nothing_to_say(report)
        return idle if idle is not None else parse(self.cli.run(briefing))


def _nothing_to_say(report: TurnReport) -> Explanation | None:
    """The answer to a turn with no decision in it, or None if there is one.

    Draw steps, upkeeps and a hand of uncastable cards are most of a game, and
    asking a model "which of these zero options is best" costs a subprocess and
    a quota call to be told what the report already says. Only taken when the
    engine understood everything on the table: with anything under CANNOT SPEAK
    FOR there *is* something to say, and saying it is the model's job.
    """
    decisions = any(card.playable for card in report.hand) or report.attacks.plans
    if decisions or report.unknown or report.attacks.caveats:
        return None
    return Explanation(
        because="Nothing here can be played or attacked with, so the turn just moves on.",
        in_short="Nothing to do right now -- pass the turn.",
    )


def parse(stdout: str) -> Explanation:
    """Turn the command's output into an explanation.

    Raises:
        ExplainerError: If there is no usable answer in there.
    """
    explanation = _explanation(object_in(stdout))
    if not explanation.because and not explanation.in_short:
        # Reached by the CLI's own error envelope, whose `result` is null: that
        # decodes to a well-formed object with none of the fields in it. Advice
        # with no words is not advice, and showing it blank would look like the
        # coach had considered the board and had nothing to say.
        msg = "the coach's answer had no explanation in it"
        raise ExplainerError(msg)
    return explanation


def _explanation(payload: Mapping[str, object]) -> Explanation:
    """Build an explanation, taking only fields of the right shape."""
    return Explanation(
        play=text(payload, "play"),
        attack=words(payload, "attack"),
        because=text(payload, "because"),
        in_short=text(payload, "in_short"),
        watch_out=words(payload, "watch_out"),
        check_yourself=words(payload, "check_yourself"),
    )
