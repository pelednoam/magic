"""Every way an explanation can disagree with the engine about a *choice*.

The prose is not one of them, and there is a deliberate absence here where a
check for it used to be. It refused any explanation whose words named a card in
hand that could not be played -- which sounds right and is wrong, because on a
turn-one hand six of seven cards cannot be played and "put down a Forest so you
can cast the Elves next turn" is the most useful sentence a coach has. Refusing
that to catch a hypothetical "cast the Dragon" traded the common good case for
a rare bad one, and it was caught by playing one real hand.

So the guarantee is exactly what it says: the *choice* agrees with the engine.
The words beside it are the part a model is for, they are unchecked, and both
the panel and the wire say so -- the checked choice is rendered above them, and
the flag is called ``trusted`` for the choice rather than for the sentence.

One function per way, each returning sentences rather than raising, because an
explanation usually fails in more than one way at once and a player is better
served by all of them than by the first. The checks about what an explanation
does *not* say are in ``silence``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.core.combat.search import Plan

#: How many attacks are put in front of the model, and therefore how many it
#: may choose from. The engine can enumerate more than a person wants to read,
#: and past a handful the tail is strictly worse than the head -- they are
#: already sorted.
#:
#: Defined here rather than in ``briefing`` because it is part of the contract
#: these checks enforce: "recommend only from the options below" has to mean
#: the options below. They disagreed once -- the prompt showed six and the
#: checker accepted any of them -- so a model could be credited with choosing a
#: plan it had never been shown.
SHOWN_ATTACKS = 6

#: How much model text a refusal may quote back. Long enough to recognise a
#: mangled instance id, short enough that a refusal stays a sentence.
_READABLE = 80


def offered(report: TurnReport) -> tuple[Plan, ...]:
    """The attacks the model was actually shown.

    The same slice ``briefing`` takes, because a checker that accepts more than
    the prompt offered credits a model with choosing something it never saw --
    and an attack past the cut is one nobody read the consequences of.
    """
    return report.attacks.plans[:SHOWN_ATTACKS]


def play(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """The card it recommends has to be one the engine says can be played."""
    if not explanation.play:
        return ()
    card = next((c for c in report.hand if str(c.instance_id) == explanation.play), None)
    if card is None:
        return (f"recommends playing {_short(explanation.play)!r}, which is not in hand",)
    if not card.playable:
        because = "; ".join(card.reasons)
        return (f"recommends playing {card.name}, which cannot be played: {because}",)
    return ()


def attack(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """The attack it recommends has to be one the engine actually evaluated.

    Matched as a *set* of identities against the enumerated plans. A model that
    invents an attack has not made a bolder choice, it has made one nobody
    worked out the consequences of -- and the consequences are the advice.

    "Attack with nobody" goes through the same match. It is a recommendation
    like any other and the engine costs it like any other -- holding back is
    always one of the enumerated plans -- so exempting it meant the one piece
    of combat advice a beginner hears most often was the one nothing checked.
    """
    if not offered(report):
        # No combat to advise on. Saying nothing about it is right rather than
        # unchecked; saying something about it is the error below.
        if not explanation.attack:
            return ()
        why = report.attacks.unavailable or "none were enumerated"
        return (f"recommends attacking, but the engine gave no plans: {why}",)
    # Sorted tuples, not sets. A set made ("bear-1", "bear-1") equal to a plan
    # attacking with one Bear, so an explanation naming the same creature twice
    # -- which is not a legal attack and is not a plan the engine costed --
    # matched one that was.
    wanted = tuple(sorted(explanation.attack))
    for plan in offered(report):
        if tuple(sorted(str(c.instance_id) for c in plan.attackers)) == wanted:
            return ()
    named = _short(", ".join(wanted))
    return (f"recommends an attack the engine did not evaluate: {named}",)


def _short(value: str) -> str:
    """Model text, cut to a length a person can read.

    These strings end up in the refusal shown on screen, and every one of them
    came out of a model -- there is no length a malformed ``play`` cannot be.
    No ``repr``: the caller decides how to present it, and wrapping a list's
    ``str`` in one produced a line of escaped quotes nobody could read.
    """
    return value if len(value) <= _READABLE else value[:_READABLE] + "..."
