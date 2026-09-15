"""Turning a decision into the events the engine actually has.

A player casting a spell does what the app's user does: taps the lands the
payment names, casts the card onto the stack, and lets it resolve. This module
does exactly that and nothing cleverer, because a harness that invented its own
rules would be testing itself.

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

from mtgcoach.api import guard
from mtgcoach.core.events import (
    CastSpell,
    ChangeLife,
    MoveCard,
    PassPriority,
    PlayLand,
    ResolveSpell,
    SetTapped,
)
from mtgcoach.core.reduce import apply
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
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


def played(
    state: GameState, player: PlayerId, card: Playable, lookup: CardLookup | None = None
) -> Applied:
    """Put this card onto the battlefield, paying for it if it is not a land.

    Raises:
        IllegalEventError: If the engine refuses any of it. Deliberately not
            caught: the caller only ever passes a card the engine has just
            called playable, so a refusal here is the engine contradicting
            itself, which is the most interesting thing this harness can find.
    """
    if card.is_land:
        return _done(state, [PlayLand(player=player, instance_id=card.instance_id)], lookup)
    return _done(state, cast_and_resolve(state, player, card), lookup)


def cast_and_resolve(state: GameState, player: PlayerId, card: Playable) -> list[Event]:
    """The four events a spell nobody answers produces.

    Casting is one event including its payment, because CR 601.2 is one action:
    announcing the spell and paying for it happen without stopping, and a spell
    half-cast is not a state the game can be in. Resolution is the last, and
    takes it off the stack -- onto the battlefield if it is a permanent spell
    (CR 608.3), into its owner's graveyard if it is an instant or a sorcery
    (CR 608.2m).

    **Between them, two passes, and they are the point.** It used to be two
    events back to back, with a note saying nothing here could respond because
    neither agent held priority and the engine had none to hold. The engine has
    priority now, so a spell resolves because every player passed in succession
    (CR 117.4) -- and the harness has to actually pass, through the reducer,
    recorded in the log, or the resolution is refused.

    The caster passes first because casting hands priority straight back to
    them (CR 117.3c), and the opponent second, which is turn order from there
    (CR 101.4) in a two-player game.

    **The opponent's pass is the harness deciding, and that is a harness
    policy rather than a rule.** None of the agents has a response to give --
    a ``Move`` names a card to play or an attack to make, and there is no
    "answer that spell" to name -- so a pass is the only thing the opponent
    could truthfully be said to do. It goes through the real event rather than
    being assumed away, so the log of a self-play game is a log a person could
    have produced, and the day an agent learns to hold a trick this is the line
    that has to change.
    """
    to = ZoneName.BATTLEFIELD if card.is_permanent else ZoneName.GRAVEYARD
    return [
        CastSpell(
            player=player,
            instance_id=card.instance_id,
            payment=card.payment.tapped if card.payment else (),
        ),
        PassPriority(player=player),
        PassPriority(player=state.opponent_of(player)),
        ResolveSpell(player=player, instance_id=card.instance_id, to=to),
    ]


def attacked(
    state: GameState, attacker: PlayerId, plan: Plan, lookup: CardLookup | None = None
) -> Applied:
    """Resolve this attack, using the engine's own numbers for what it does.

    Order matters and is the order the rules use: damage, then deaths, then the
    life anything gained. Doing deaths first would move a creature to the
    graveyard before it had dealt its damage, which is not what happens and --
    more to the point here -- would quietly disagree with the ``Outcome`` the
    coach showed the player a moment earlier.
    """
    defender = state.opponent_of(attacker)
    outcome = plan.outcome
    events: list[Event] = list(_tapped_to_attack(attacker, plan))
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
    return _done(state, events, lookup)


def _tapped_to_attack(attacker: PlayerId, plan: Plan) -> list[Event]:
    """Attacking taps the attackers (CR 508.1f), unless they have vigilance.

    The declaration itself is not an event this engine has -- there is no
    "attacking" state on a permanent yet -- but its most visible consequence
    is, and leaving it out was worse than modelling it partly: a creature that
    attacked and survived stayed untapped, so the recorded game showed it
    available for a second attack, or to pay for a spell, on a board where it
    was lying sideways on the table.

    Vigilance is checked rather than assumed. Thirteen of the Beginner Box's
    creatures have it, so tapping unconditionally would have been a new wrong
    answer in place of the old one.
    """
    return [
        SetTapped(player=attacker, instance_id=creature.instance_id, tapped=True)
        for creature in plan.attackers
        if not creature.card.has("vigilance")
    ]


def _died(player: PlayerId, lost: Sequence[Creature]) -> list[Event]:
    """One side's losses, on their way to the graveyard."""
    return [
        MoveCard(player=player, instance_id=creature.instance_id, to=ZoneName.GRAVEYARD)
        for creature in lost
    ]


def _done(state: GameState, events: Sequence[Event], lookup: CardLookup | None) -> Applied:
    """Apply these in order, and hand back both the result and the log.

    The log is what makes a game *replayable by anything*: the journal records
    it, and the API rebuilds any moment with `core.reduce.replay` alone. That
    keeps the replay exact -- the board is what the events produced, not a
    re-derivation that a later change to the engine could quietly alter.

    **Through the same guard the server puts in front of a player.** The
    harness used to call the reducer directly, so it exercised every check in
    ``core`` and none of the card-aware ones in ``api.guard`` -- and a whole
    class of defect could pass a three-hundred-game season while failing the
    first tap in the app. One did: casting was refused over HTTP for every
    paid spell, and a season had just applied three thousand of them.

    ``lookup`` is optional only so that a test building one event by hand need
    not have a catalogue. A real game always passes one, and
    ``test_applying_is_guarded`` is what keeps that true.
    """
    for event in events:
        if lookup is not None:
            guard.check(event, state, lookup)
        state = apply(state, event)
    return Applied(state, tuple(events))
