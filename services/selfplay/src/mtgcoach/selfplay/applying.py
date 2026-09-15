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

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.core.events import ChangeLife, MoveCard, PlayLand, SetTapped
from mtgcoach.core.reduce import apply
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.report import Playable
    from mtgcoach.core.combat.model import Creature
    from mtgcoach.core.combat.search import Plan
    from mtgcoach.core.events import Event
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState


@dataclass(frozen=True, slots=True)
class Applied:
    """A state, and the events that got it there."""

    state: GameState
    events: tuple[Event, ...]


def played(state: GameState, player: PlayerId, card: Playable) -> Applied:
    """Put this card onto the battlefield, paying for it if it is not a land.

    Raises:
        IllegalEventError: If the engine refuses any of it. Deliberately not
            caught: the caller only ever passes a card the engine has just
            called playable, so a refusal here is the engine contradicting
            itself, which is the most interesting thing this harness can find.
    """
    if card.is_land:
        return _done(state, [PlayLand(player=player, instance_id=card.instance_id)])
    paying = [
        SetTapped(player=player, instance_id=source, tapped=True)
        for source in (card.payment.tapped if card.payment else ())
    ]
    casting = MoveCard(player=player, instance_id=card.instance_id, to=ZoneName.BATTLEFIELD)
    return _done(state, [*paying, casting])


def attacked(state: GameState, attacker: PlayerId, plan: Plan) -> Applied:
    """Resolve this attack, using the engine's own numbers for what it does.

    Order matters and is the order the rules use: damage, then deaths, then the
    life anything gained. Doing deaths first would move a creature to the
    graveyard before it had dealt its damage, which is not what happens and --
    more to the point here -- would quietly disagree with the ``Outcome`` the
    coach showed the player a moment earlier.
    """
    defender = state.opponent_of(attacker)
    outcome = plan.outcome
    events: list[Event] = []
    if outcome.damage_to_defender:
        events.append(ChangeLife(player=defender, amount=-outcome.damage_to_defender))
    events += _died(attacker, outcome.attackers_lost)
    events += _died(defender, outcome.blockers_lost)
    events += [
        ChangeLife(player=player, amount=gained)
        for player, gained in (
            (attacker, outcome.attacker_life_gained),
            (defender, outcome.defender_life_gained),
        )
        if gained
    ]
    return _done(state, events)


def _died(player: PlayerId, lost: Sequence[Creature]) -> list[Event]:
    """One side's losses, on their way to the graveyard."""
    return [
        MoveCard(player=player, instance_id=creature.instance_id, to=ZoneName.GRAVEYARD)
        for creature in lost
    ]


def _done(state: GameState, events: Sequence[Event]) -> Applied:
    """Apply these in order, and hand back both the result and the log.

    The log is what makes a game *replayable by anything*: the journal records
    it, and the API rebuilds any moment with `core.reduce.replay` alone. That
    keeps the replay exact -- the board is what the events produced, not a
    re-derivation that a later change to the engine could quietly alter.
    """
    for event in events:
        state = apply(state, event)
    return Applied(state, tuple(events))
