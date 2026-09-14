"""Reading an agent's move against what the engine actually offered.

Split from ``playing`` because it is a different question. That module walks a
game; this one decides whether a decision is one the engine would recognise --
and refusing here is what stops a bad agent producing an illegal state, which
would make every later finding in the season its fault rather than the
engine's.

For the coach, a refusal here means something sharper: it recommended a card
the engine did not offer, or an attack it never costed. That is the same thing
``advice.verify`` refuses on a player's behalf.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.coach.report import Playable, TurnReport
    from mtgcoach.core.combat.search import Plan
    from mtgcoach.core.ids import InstanceId


def offered(report: TurnReport, instance: InstanceId) -> Playable:
    """The playable card the agent named.

    Raises:
        LookupError: If the agent named something that is not in hand or not
            playable. Recorded as trouble by the caller, which is the point --
            for Claude it means the coach recommended a card the engine did
            not offer.
    """
    found = next((card for card in report.playable if card.instance_id == instance), None)
    if found is None:
        msg = f"{instance} is not a playable card this turn"
        raise LookupError(msg)
    return found


def planned(report: TurnReport, attackers: tuple[InstanceId, ...]) -> Plan:
    """The engine's plan for exactly these attackers.

    Raises:
        LookupError: If no plan matches. The harness applies the *engine's*
            outcome, so an attack it never costed has no numbers to apply --
            and an agent inventing one is exactly what ``advice.verify``
            refuses on the player's behalf.
    """
    wanted = set(attackers)
    for plan in report.attacks.plans:
        if {creature.instance_id for creature in plan.attackers} == wanted:
            return plan
    msg = f"no costed attack with exactly {sorted(wanted)}"
    raise LookupError(msg)
