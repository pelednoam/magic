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

It also will not *raise* one. Every refusal the engine makes becomes a sentence
in a report -- a reason on a card, or ``Attacks.unavailable``. Letting one
escape turned the whole snapshot into a 500, and since the API records an event
before building the advice, a single accepted event could leave a game that
could never be read again.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import partial
from typing import TYPE_CHECKING

from mtgcoach.coach import mana
from mtgcoach.coach.attacks import Attacks, attacks_for
from mtgcoach.coach.speaking import named_by, unknown_to
from mtgcoach.coach.warnings import reminders as warnings_for
from mtgcoach.core.disclosure import disclosures
from mtgcoach.core.legality import why_not_cast, why_not_play_land
from mtgcoach.core.manasolver import payments

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import InstanceId, PlayerId
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
    #: Whether playing this is a land drop. The client needs it because playing
    #: a land (CR 305.1) and casting a spell (CR 601) are different actions
    #: with different events, and only one of them is a land drop.
    is_land: bool = False
    #: What the engine will *not* do if you play this, in words, and empty when
    #: it will do all of it.
    #:
    #: A different question from ``reasons``, which is why you cannot play the
    #: card. You can play Giant Growth; the tracker simply will not change
    #: anybody's toughness when you do, and every number it shows afterwards is
    #: computed from a board that is wrong by three points. The card used to
    #: come back playable with nothing said, because its effect is *described*
    #: in the fixture and being described is what ``modelled`` measures.
    not_carried_out: tuple[str, ...] = ()
    #: Whether casting this puts a permanent on the battlefield (CR 608.3) or
    #: sends the card to its owner's graveyard as it resolves (CR 608.2m). The
    #: client needs it because ``ResolveSpell`` has to be told which, and it is
    #: the only party that knows: ``core`` cannot read a type line.
    is_permanent: bool = False
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
    #: What the *rules engine* does not model at this moment, in its own words.
    #:
    #: The same disclosure ``unknown`` makes about cards, made about the rules.
    #: ``unknown`` and ``Playable.not_carried_out`` cover a card the engine
    #: cannot speak for; nothing covered a rule it cannot, and the priority
    #: model is the first place that gap is visible to a player -- a stack that
    #: holds only spells looks complete, and a child who learned from it that a
    #: trigger cannot be answered would have learned something that is not a
    #: rule of Magic. See ``core.disclosure``.
    not_modelled: tuple[str, ...] = ()

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
        reminders=warnings_for(
            state, player, lookup, partial(named_by, lookup), your_turn=your_turn
        ),
        unknown=unknown_to(state, player_id, lookup),
        not_modelled=disclosures(state),
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
    undone = lookup.not_carried_out(card.oracle_id)
    if facts.is_land:
        reasons = why_not_play_land(state, player_id, facts)
        return Playable(
            card.instance_id,
            facts.name,
            not_carried_out=undone,
            is_land=True,
            reasons=reasons,
        )
    spell = partial(
        Playable,
        card.instance_id,
        facts.name,
        not_carried_out=undone,
        is_permanent=facts.is_permanent,
    )
    try:
        reasons = why_not_cast(state, player_id, facts, sources)
        best = payments(facts.cost, sources) if not reasons else ()
    except ValueError as refusal:
        # The solver refuses a board it cannot answer for exactly -- too many
        # untapped sources, or two sharing an identity. That is a *reason*
        # here, not an error: letting it escape made the whole snapshot a 500,
        # and because the event is recorded before the advice is built, one
        # accepted event left the game permanently unreadable.
        return spell(reasons=(str(refusal),))
    return spell(reasons=reasons, payment=best[0] if best else None)
