"""Asking Claude what to do about a turn.

The prompt comes from the engine's report and the answer goes straight to
``advice.verify``, which decides whether any of it may be shown. This module
only turns one into the other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.api.claude import Cli
from mtgcoach.api.fields import exactly, one, prose, words
from mtgcoach.api.replies import object_in
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
    a quota call to be told what the report already says.

    Only taken when there is genuinely nothing. Three things count as something,
    and the third was a bug: a card the engine cannot read, a combat caveat, and
    **a trigger about to fire**. An upkeep with a trigger on it has no playable
    card and no attack plan, so the shortcut fired and said "pass the turn" --
    while the panel two inches away said the trigger was happening now. Telling
    a nine-year-old to pass through their own trigger is exactly the confidently
    wrong answer this layer exists to prevent, and it came from the side of the
    layer that never asked a model anything.
    """
    decisions = any(card.playable for card in report.hand) or report.attacks.plans
    if decisions or report.reminders or report.unknown or report.attacks.caveats:
        return None
    return Explanation(
        because=(
            "Nothing here can be played or attacked with, so this step has no "
            "decision in it. Move on to the next one."
        ),
        # Not "pass the turn". Most of the steps this fires on are an upkeep or
        # a draw, where passing the *turn* means skipping the main phase -- so
        # the shortcut for "there is nothing to decide here" was telling a
        # beginner to give up their whole turn.
        in_short="Nothing to do in this step. Go to the next one.",
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
        # Both demanded: see `fields._missing`. A reply missing one of them
        # used to become "do nothing", which the engine agrees with often
        # enough to come out `trusted`.
        play=one(payload, "play"),
        attack=exactly(payload, "attack", required=True),
        because=prose(payload, "because"),
        in_short=prose(payload, "in_short"),
        watch_out=words(payload, "watch_out"),
        check_yourself=words(payload, "check_yourself"),
    )
