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

from mtgcoach.coach import statics
from mtgcoach.core.combat.model import Creature
from mtgcoach.core.combat.search import plans
from mtgcoach.core.legality import why_not_declare_attackers

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.abilities import Ability
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
    #: What is on the table that the numbers do not account for. Not a reason
    #: to show nothing -- the plans are still the best available -- but the
    #: player has to read "four damage, lethal" as "unless the Pacifism says
    #: otherwise". A confident wrong number is worse than a hedged one.
    caveats: tuple[str, ...] = ()


def attacks_for(state: GameState, player_id: PlayerId, lookup: CardLookup) -> Attacks:
    """The attacks worth making, or why the question does not arise."""
    blocked = why_not_declare_attackers(state, player_id)
    if blocked:
        return Attacks(unavailable=blocked[0])
    mine = state.player(player_id).battlefield
    theirs = [s.battlefield for pid, s in state.players.items() if pid != player_id]
    attackers = _creatures(mine, lookup, restricted=statics.cannot_attack)
    defenders = tuple(
        creature
        for battlefield in theirs
        for creature in _creatures(battlefield, lookup, restricted=statics.cannot_block)
    )
    unaccounted = statics.caveats([mine, *theirs], lookup)
    defender_life = min(
        (other.life for pid, other in state.players.items() if pid != player_id),
        default=0,
    )
    try:
        return Attacks(plans=plans(attackers, defenders, defender_life), caveats=unaccounted)
    except ValueError as refusal:
        # The engine refuses rather than guesses -- an unknown power, a repeated
        # identity, a board too large to search exactly. Passing the refusal on
        # is the point: a blank attack section would read as "do not attack".
        return Attacks(unavailable=str(refusal), caveats=unaccounted)


def _creatures(
    battlefield: Sequence[Permanent],
    lookup: CardLookup,
    restricted: Callable[[Sequence[Ability]], bool],
) -> tuple[Creature, ...]:
    """The creatures on a battlefield that could take this side of a combat.

    Two exclusions, for two different reasons. A permanent the fixture cannot
    speak for is left out rather than guessed at -- and still reaches the
    player, through ``unknown``. A creature whose own static ability forbids
    this side of combat is left out because it *is* the rule: Vampire
    Interloper cannot block, and counting it as a blocker would make every
    attack look worse than it is.
    """
    found: list[Creature] = []
    for permanent in battlefield:
        card = lookup.facts(permanent.card.oracle_id)
        if card is None or not card.is_creature:
            continue
        if restricted(lookup.abilities(permanent.card.oracle_id)):
            continue
        found.append(Creature(permanent, card))
    return tuple(found)
