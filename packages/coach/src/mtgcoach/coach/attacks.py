"""Which attacks are worth making, or why the question does not arise.

Its own module because "can I attack at all?" and "which attack is best?" are
different questions with different answers, and because the interesting part is
the third case: the engine *refusing*. A board it cannot evaluate exactly
returns a sentence, not an empty list -- an empty attack section reads as "do
not attack", which is advice, and the wrong advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.core.combat.model import Creature
from mtgcoach.core.combat.search import plans
from mtgcoach.core.legality import why_not_declare_attackers

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.combat.search import Plan
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.state import GameState


@dataclass(frozen=True, slots=True)
class Attacks:
    """The attacks worth considering, or why there are none to show."""

    plans: tuple[Plan, ...] = ()
    #: Why the section is empty, when it is empty for a reason worth saying --
    #: "it is not your combat", or a board too large to evaluate exactly.
    unavailable: str = ""


def attacks_for(state: GameState, player_id: PlayerId, lookup: CardLookup) -> Attacks:
    """The attacks worth making, or why the question does not arise."""
    blocked = why_not_declare_attackers(state, player_id)
    if blocked:
        return Attacks(unavailable=blocked[0])
    attackers = _creatures(state.player(player_id).battlefield, lookup)
    defenders = tuple(
        creature
        for other, other_state in state.players.items()
        if other != player_id
        for creature in _creatures(other_state.battlefield, lookup)
    )
    defender_life = min(
        (other.life for pid, other in state.players.items() if pid != player_id),
        default=0,
    )
    try:
        return Attacks(plans=plans(attackers, defenders, defender_life))
    except ValueError as refusal:
        # The engine refuses rather than guesses -- an unknown power, a repeated
        # identity, a board too large to search exactly. Passing the refusal on
        # is the point: a blank attack section would read as "do not attack".
        return Attacks(unavailable=str(refusal))


def _creatures(battlefield: Sequence[Permanent], lookup: CardLookup) -> tuple[Creature, ...]:
    """The creatures on a battlefield, as combat wants them.

    A permanent the fixture cannot speak for is left out rather than guessed at.
    It still reaches the player, through ``unknown``.
    """
    found: list[Creature] = []
    for permanent in battlefield:
        card = lookup.facts(permanent.card.oracle_id)
        if card is not None and card.is_creature:
            found.append(Creature(permanent, card))
    return tuple(found)
