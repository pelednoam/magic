"""Turning a decision into the events the engine actually has.

The engine has no event for *casting* a spell -- ``Playable`` says so in as
many words, and the stack arrives with it -- so a player casting a creature
does what the app's user does: taps the lands the payment names, and moves the
card onto the battlefield. This module does exactly that and nothing cleverer,
because a harness that invented its own rules would be testing itself.

The same principle decides combat. The engine does not apply damage, it
*computes* it: ``Outcome`` says how much the defender takes, which creatures
die, and what life is gained. This applies those numbers. Where the engine is
the authority the engine is asked; where it has no answer -- which blocks the
defender would actually choose -- the engine's own assumption is used, which is
that the defender blocks as well as they can.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.events import ChangeLife, MoveCard, PlayLand, SetTapped
from mtgcoach.core.reduce import apply
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.coach.report import Playable
    from mtgcoach.core.combat.search import Plan
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState


def played(state: GameState, player: PlayerId, card: Playable) -> GameState:
    """Put this card onto the battlefield, paying for it if it is not a land.

    Raises:
        IllegalEventError: If the engine refuses any of it. Deliberately not
            caught: the caller only ever passes a card the engine has just
            called playable, so a refusal here is the engine contradicting
            itself, which is the most interesting thing this harness can find.
    """
    if card.is_land:
        return apply(state, PlayLand(player=player, instance_id=card.instance_id))
    for source in card.payment.tapped if card.payment else ():
        state = apply(state, SetTapped(player=player, instance_id=source, tapped=True))
    return apply(
        state,
        MoveCard(player=player, instance_id=card.instance_id, to=ZoneName.BATTLEFIELD),
    )


def attacked(state: GameState, attacker: PlayerId, plan: Plan) -> GameState:
    """Resolve this attack, using the engine's own numbers for what it does.

    Order matters and is the order the rules use: damage, then deaths, then the
    life anything gained. Doing deaths first would move a creature to the
    graveyard before it had dealt its damage, which is not what happens and --
    more to the point here -- would quietly disagree with the ``Outcome`` the
    coach showed the player a moment earlier.
    """
    defender = state.opponent_of(attacker)
    outcome = plan.outcome
    if outcome.damage_to_defender:
        state = apply(state, ChangeLife(player=defender, amount=-outcome.damage_to_defender))
    state = _died(state, attacker, plan)
    state = _died(state, defender, plan, blockers=True)
    for player, gained in (
        (attacker, outcome.attacker_life_gained),
        (defender, outcome.defender_life_gained),
    ):
        if gained:
            state = apply(state, ChangeLife(player=player, amount=gained))
    return state


def _died(state: GameState, player: PlayerId, plan: Plan, *, blockers: bool = False) -> GameState:
    """Move one side's losses to the graveyard."""
    lost = plan.outcome.blockers_lost if blockers else plan.outcome.attackers_lost
    for creature in lost:
        state = apply(
            state,
            MoveCard(
                player=player,
                instance_id=creature.instance_id,
                to=ZoneName.GRAVEYARD,
            ),
        )
    return state
