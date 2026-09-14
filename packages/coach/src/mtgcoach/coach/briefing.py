"""What the model is told, and what it is told not to do.

The prompt is built from the engine's own report, so every fact in it has
already been checked. That is the point: the model is not asked what is legal,
it is handed what is legal and asked which of it is *wise*, and why, in words a
nine-year-old can use.

Written as plain text rather than JSON because the reader is a language model
and the difference is a few hundred tokens of clarity. The *reply* is JSON,
because that one is read by a program.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.coach.checks import SHOWN_ATTACKS

if TYPE_CHECKING:
    from mtgcoach.coach.report import TurnReport

RULES = """\
You are helping a parent teach a nine-year-old to play Magic: The Gathering.

A rules engine has already worked out what is legal. You are not being asked
what the rules are -- you are being given the legal options and asked which one
is best, and why.

Hard rules, in order of importance:

1. Recommend only from the options below. If you name a card to play, it must
   be one marked PLAYABLE. If you name an attack, it must be one of the numbered
   attacks, and you must give exactly its creatures. Anything else is discarded
   unread, and the player sees nothing.
   You may talk about a card you are *not* recommending -- "a land now means
   the Elves next turn" is exactly the kind of thing worth saying -- but make
   it unmistakable that it is about a later turn, not this one. Your words are
   what the player reads, and nothing checks them.
2. Never state a rule the options do not already state. If you want to explain
   why something works, explain it from what is here.
3. Anything under CANNOT SPEAK FOR must appear in check_yourself. The engine
   does not understand those cards; saying nothing about them would let the
   player think they were counted.
4. Anything under TRIGGERS NOW must be named somewhere in your answer, by the
   card's name. Those abilities are happening whether or not anybody notices,
   and a beginner who is not told will miss them. An answer that does not
   mention them is discarded, like one that invents a card.
5. "in_short" is for the child. Short sentences, no jargon, no numbers they
   would have to hold in their head. "Their creature is bigger, so yours would
   just die" -- not "unfavourable trade at parity".

Reply with this JSON object and nothing else:

{"play": "<instance_id or empty>",
 "attack": ["<instance_id>", ...],
 "because": "<2-3 sentences for the adult>",
 "in_short": "<1-2 sentences for the child>",
 "watch_out": ["<something that will go wrong if unnoticed>"],
 "check_yourself": ["<something the engine could not work out>"]}
"""


def brief(report: TurnReport) -> str:
    """The whole prompt for one turn."""
    return "\n".join(
        [
            RULES,
            _where(report),
            _hand(report),
            _attacks(report),
            _reminders(report),
            _gaps(report),
        ]
    )


def _where(report: TurnReport) -> str:
    """Where in the turn this is."""
    whose = "your turn" if report.your_turn else "their turn"
    return (
        f"\nWHERE: turn {report.turn}, {report.step.value}, {whose}. You are on {report.life} life."
    )


def _hand(report: TurnReport) -> str:
    """Every card in hand and the engine's verdict on it."""
    if not report.hand:
        return "\nHAND: empty."
    lines = ["\nHAND:"]
    for card in report.hand:
        if card.playable:
            how = ""
            if card.payment is not None:
                how = f" (tap {len(card.payment.tapped)}, keeps {len(card.payment.spare)} up)"
            lines.append(f"  PLAYABLE  {card.instance_id}  {card.name}{how}")
        else:
            lines.append(f"  no        {card.name}: {'; '.join(card.reasons)}")
    return "\n".join(lines)


def _attacks(report: TurnReport) -> str:
    """The attacks the engine evaluated, best first, with the maths."""
    if report.attacks.unavailable:
        return f"\nATTACKS: none to consider -- {report.attacks.unavailable}"
    lines = ["\nATTACKS (best first, the engine worked these out exactly):"]
    for index, plan in enumerate(report.attacks.plans[:SHOWN_ATTACKS], 1):
        who = ", ".join(f"{c.name} [{c.instance_id}]" for c in plan.attackers) or "nobody"
        outcome = [f"{plan.outcome.damage_to_defender} damage"]
        if plan.is_lethal:
            outcome.append("THIS WINS THE GAME")
        else:
            outcome.append(f"they go to {plan.defender_life_after}")
        if plan.outcome.blocker_names:
            outcome.append(f"kills {', '.join(plan.outcome.blocker_names)}")
        if plan.outcome.attacker_names:
            outcome.append(f"you lose {', '.join(plan.outcome.attacker_names)}")
        lines.append(f"  {index}. {who} -- {'; '.join(outcome)}")
    return "\n".join(lines)


def _reminders(report: TurnReport) -> str:
    """Triggers about to be missed.

    The instruction that goes with this is rule 4 above, and the two were added
    a round apart: the checker demanded that every one of these be named before
    the prompt ever asked for it, which would have refused every turn with a
    trigger on it. A requirement nobody was told about is not a requirement, it
    is a trap.
    """
    if not report.reminders:
        return ""
    names = ", ".join(r.name for r in report.reminders)
    return f"\nTRIGGERS NOW (name every one of these in your answer): {names}"


def _gaps(report: TurnReport) -> str:
    """Everything the engine could not work out, which must be passed on."""
    owed = (*report.unknown, *report.attacks.caveats)
    if not owed:
        return "\nCANNOT SPEAK FOR: nothing -- every card here is fully modelled."
    listed = "\n".join(f"  - {item}" for item in owed)
    return (
        "\nCANNOT SPEAK FOR (these are NOT in the numbers above; every one of\n"
        "them must appear in check_yourself):\n" + listed
    )
