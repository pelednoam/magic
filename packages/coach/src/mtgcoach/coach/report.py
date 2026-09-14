"""What you can do this turn, and what the coach cannot speak for.

The four solvers each answer a narrow question. This assembles them into the one
a player actually asks, and it is the shape §3's Tier 1 describes: every card in
hand with a verdict, the land drop, the attacks worth making, the triggers about
to be missed.

Two things it will not do. It will not answer for a card the fixture does not
model -- those are named in ``unknown``, so the player knows exactly where the
coach stops rather than being quietly told "no". And it will not swallow a
refusal from the engine: if the board is too large to search exactly, the attack
section says so instead of showing a guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.coach import mana
from mtgcoach.coach.attacks import Attacks, attacks_for
from mtgcoach.core.legality import why_not_cast, why_not_play_land
from mtgcoach.core.manasolver import payments
from mtgcoach.core.triggerscan import triggers_at

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
    from mtgcoach.core.manacost import ManaSource
    from mtgcoach.core.manasolver import Payment
    from mtgcoach.core.state import GameState
    from mtgcoach.core.steps import Step
    from mtgcoach.core.triggerscan import Reminder


@dataclass(frozen=True, slots=True)
class Playable:
    """One card in hand, and whether you can play it."""

    instance_id: InstanceId
    name: str
    #: Empty when you can play it. Otherwise every reason you cannot, in the
    #: engine's own words -- "you need 1 more untapped source", not False.
    reasons: tuple[str, ...] = ()
    #: The best way to pay, when it can be paid. The *best* is the one that
    #: keeps the most colours untapped, which is the advice a beginner never
    #: gets: not "you can cast this" but "cast it with these, keep the Island".
    payment: Payment | None = None

    @property
    def playable(self) -> bool:
        """Whether this can be played right now."""
        return not self.reasons


@dataclass(frozen=True, slots=True)
class TurnReport:
    """Everything the coach has to say about this moment."""

    turn: int
    step: Step
    your_turn: bool
    life: int
    hand: tuple[Playable, ...] = ()
    attacks: Attacks = field(default_factory=Attacks)
    reminders: tuple[Reminder, ...] = ()
    #: Cards on the table or in hand the fixture has no model for. Named, not
    #: hidden: the honest failure is "I can't speak for this one", and a beginner
    #: who is not told that will read silence as "there is nothing to do".
    unknown: tuple[str, ...] = ()

    @property
    def playable(self) -> tuple[Playable, ...]:
        """The cards you could actually play, best first is not this layer's job."""
        return tuple(card for card in self.hand if card.playable)


def advise(state: GameState, player_id: PlayerId, lookup: CardLookup) -> TurnReport:
    """Assemble everything the engine can say about this player's position.

    Raises:
        IllegalEventError: If ``player_id`` is not in this game.
    """
    player = state.player(player_id)
    sources = mana.available(player.battlefield, lookup)
    your_turn = state.active_player == player_id
    return TurnReport(
        turn=state.turn,
        step=state.step,
        your_turn=your_turn,
        life=player.life,
        hand=tuple(_verdict(state, player_id, card, sources, lookup) for card in player.hand),
        attacks=attacks_for(state, player_id, lookup),
        reminders=triggers_at(
            state.step,
            player.battlefield,
            lookup.abilities,
            lambda oracle_id: _name(lookup, oracle_id),
            your_turn=your_turn,
        ),
        unknown=_unknown(state, player_id, lookup),
    )


def _verdict(
    state: GameState,
    player_id: PlayerId,
    card: CardInstance,
    sources: Sequence[ManaSource],
    lookup: CardLookup,
) -> Playable:
    """Whether this card can be played now, and how to pay for it."""
    facts = lookup.facts(card.oracle_id)
    if facts is None:
        return Playable(
            card.instance_id,
            str(card.oracle_id),
            reasons=("this card is not modelled, so the coach cannot say",),
        )
    if facts.is_land:
        reasons = why_not_play_land(state, player_id, facts)
        return Playable(card.instance_id, facts.name, reasons=reasons)
    reasons = why_not_cast(state, player_id, facts, sources)
    best = payments(facts.cost, sources) if not reasons else ()
    return Playable(
        card.instance_id,
        facts.name,
        reasons=reasons,
        payment=best[0] if best else None,
    )


def _unknown(state: GameState, player_id: PlayerId, lookup: CardLookup) -> tuple[str, ...]:
    """Every card in this player's view the fixture cannot speak for."""
    player = state.player(player_id)
    seen = [c.oracle_id for c in player.hand]
    seen += [p.card.oracle_id for p in player.battlefield]
    return tuple(sorted({str(o) for o in seen if lookup.facts(o) is None}))


def _name(lookup: CardLookup, oracle_id: OracleId) -> str:
    """A card's name, falling back to its identifier when it is unknown."""
    facts = lookup.facts(oracle_id)
    return facts.name if facts is not None else str(oracle_id)
