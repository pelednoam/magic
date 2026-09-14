"""What a coach may say, and how we know it did not make it up.

§8: the engine decides what is *legal*; Claude decides what is *wise* and says
it in words a child understands. Claude is never the source of truth for rules.

That is easy to write down and hard to enforce, because a fluent wrong answer
reads exactly like a fluent right one. So an explanation is not prose here: it
is a *choice among options the engine already enumerated*, plus words about it.
The choice can be checked, and ``verify`` checks it -- a recommendation to
attack with a creature that was not in any plan, or to cast a card the engine
said cannot be cast, is rejected before anyone reads it.

What cannot be checked is the prose. That is the part a model is actually for,
and it is also why the honesty rules in §8 are enforced structurally rather than
asked for politely: if the engine could not speak for a card, the explanation
has to say so, and ``verify`` fails it when it does not.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from mtgcoach.coach import checks, silence

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.report import TurnReport


@dataclass(frozen=True, slots=True)
class Explanation:
    """One turn's advice, as a choice plus the words for it."""

    #: The card to play, by instance id. Empty when the advice is to play none.
    play: str = ""
    #: The creatures to attack with, by instance id. Empty means do not attack,
    #: which is a real recommendation and not an absence of one.
    attack: tuple[str, ...] = ()
    #: Why, for whoever is teaching.
    because: str = ""
    #: The same thing for the person being taught. §3's whole point.
    in_short: str = ""
    #: Things that will go wrong if they are not noticed.
    watch_out: tuple[str, ...] = field(default_factory=tuple[str, ...])
    #: Things the engine could not verify and the player must check on the
    #: card. Never empty when the report has anything it could not speak for.
    check_yourself: tuple[str, ...] = field(default_factory=tuple[str, ...])


class Explainer(Protocol):
    """Something that turns a turn report into words. A model, usually."""

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """Advise on this turn.

        Raises:
            ExplainerError: If no explanation could be obtained.
        """
        ...


class ExplainerError(RuntimeError):
    """No explanation could be got. The engine's own panel still stands."""


def verify(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """Every way this explanation disagrees with the engine, empty when none.

    Not a style check. Each of these is a way a fluent answer can be wrong
    about the rules, which is the one thing this layer must never be. They live
    in ``checks``; this is the list of them.
    """
    return (
        *checks.play(explanation, report),
        *checks.attack(explanation, report),
        *silence.honesty(explanation, report),
        *silence.triggers(explanation, report),
        *checks.prose(explanation, report),
    )


def trusted(explanation: Explanation, report: TurnReport) -> bool:
    """Whether this explanation can be shown as advice."""
    return not verify(explanation, report)


def refusal(problems: Sequence[str]) -> Explanation:
    """What to show instead of an explanation that failed its checks.

    Not silence, and not the broken advice. The engine's own panel is still on
    screen and still right; this says why the words next to it are missing.
    """
    return Explanation(
        because="The coach's answer disagreed with the rules engine, so it is not shown.",
        in_short="I got confused there. Use the lists above -- those are checked.",
        watch_out=tuple(problems),
    )
