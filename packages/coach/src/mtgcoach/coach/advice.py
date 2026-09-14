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
    about the rules, which is the one thing this layer must never be.
    """
    return (
        *_check_play(explanation, report),
        *_check_attack(explanation, report),
        *_check_honesty(explanation, report),
    )


def _check_play(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """The card it recommends has to be one the engine says can be played."""
    if not explanation.play:
        return ()
    card = next((c for c in report.hand if str(c.instance_id) == explanation.play), None)
    if card is None:
        return (f"recommends playing {explanation.play!r}, which is not in hand",)
    if not card.playable:
        because = "; ".join(card.reasons)
        return (f"recommends playing {card.name}, which cannot be played: {because}",)
    return ()


def _check_attack(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """The attack it recommends has to be one the engine actually evaluated.

    Matched as a *set* of identities against the enumerated plans. A model that
    invents an attack has not made a bolder choice, it has made one nobody
    worked out the consequences of -- and the consequences are the advice.
    """
    if not explanation.attack:
        return ()
    if report.attacks.unavailable:
        return (
            f"recommends attacking, but the engine gave no plans: {report.attacks.unavailable}",
        )
    # Sorted tuples, not sets. A set made ("bear-1", "bear-1") equal to a plan
    # attacking with one Bear, so an explanation naming the same creature twice
    # -- which is not a legal attack and is not a plan the engine costed --
    # matched one that was.
    wanted = tuple(sorted(explanation.attack))
    for plan in report.attacks.plans:
        if tuple(sorted(str(c.instance_id) for c in plan.attackers)) == wanted:
            return ()
    return (f"recommends an attack the engine did not evaluate: {list(wanted)}",)


def _check_honesty(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """Where the engine stops, the explanation has to say so -- about each card.

    §8: "If the engine hits an ``Unmodeled`` effect, say so and show the card
    text." Asked for in the prompt and enforced here, because a model that
    forgets is indistinguishable from one that decided the card did not matter.

    Checked *per card*, not as a count. Requiring only that ``check_yourself``
    be non-empty meant one arbitrary sentence discharged every obligation on
    the board: a model that mentioned the Pacifism and said nothing about the
    Equipment passed, and the player read the silence as "counted".
    """
    owed = (*report.unknown, *report.attacks.caveats)
    said = " ".join(explanation.check_yourself).casefold()
    missing = [item for item in owed if _named(item).casefold() not in said]
    if not missing:
        return ()
    return (f"says nothing about {len(missing)} of {len(owed)} not modelled: {missing[:3]}",)


def _named(item: str) -> str:
    """The card an unmodelled-thing sentence is about.

    Both producers write "<name>: <reason>" -- ``report._unknown`` and
    ``statics.caveats``. The name is what a model would repeat; the reason is
    the engine's own words and asking for those back would be asking it to
    quote us.
    """
    return item.split(":", 1)[0].strip()


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
        in_short="I got confused there. Use the list on the left -- that part is checked.",
        watch_out=tuple(problems),
    )
