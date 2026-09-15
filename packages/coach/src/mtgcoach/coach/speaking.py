"""Which cards the coach cannot speak for, and how to name one it cannot.

Split from ``report`` at the line limit. The seam is between *judging* a board
and saying what the judgement does not cover, which are different jobs -- and
this one is the disclosure half, which matters more than its size suggests.

There are three claims about a card and they are not the same:

- **Identified.** ``facts`` knows its name, cost and types.
- **Described.** ``modelled`` -- its behaviour is in the sealed fixture. 65 of
  the Beginner Box's 124 cards.
- **Carried out.** ``not_carried_out`` -- the engine actually does that
  behaviour. Far fewer, because the reducer has no effect execution at all.

This list is the first two. The third is reported per card, on the card, where
it is actionable: "some things are not modelled" is not, and "the tracker will
not apply its +3/+3 -- do it on the table" is.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.ids import OracleId, PlayerId
    from mtgcoach.core.state import GameState


def unknown_to(state: GameState, player_id: PlayerId, lookup: CardLookup) -> tuple[str, ...]:
    """Every card in this player's view the engine cannot speak for.

    Two different failures, and the second one used to be invisible. A card with
    no *facts* cannot be identified at all. A card with facts but no complete
    *model* can be identified and priced, and the engine still does not know
    what it does -- which is 59 of the Beginner Box's 124 cards. Reporting only
    the first meant the coach gave confident advice about half the box while
    ``unknown`` stayed empty, which is the one thing this field exists to stop.
    """
    player = state.player(player_id)
    seen = [c.oracle_id for c in player.hand]
    # Every battlefield, not just this player's. An opposing creature the coach
    # cannot identify is left out of combat silently, so the attack advisor
    # reported exact damage and "no blockers" against a board it could not see.
    # Their battlefield is public; their *hand* is not, and is not looked at.
    seen += [p.card.oracle_id for other in state.players.values() for p in other.battlefield]
    return tuple(sorted({named_by(lookup, o) for o in seen if not _spoken_for(lookup, o)}))


def _spoken_for(lookup: CardLookup, oracle_id: OracleId) -> bool:
    """Whether the engine can answer for this card at all."""
    return lookup.facts(oracle_id) is not None and lookup.modelled(oracle_id)


def named_by(lookup: CardLookup, oracle_id: OracleId) -> str:
    """A card's name, falling back to its identifier when it is unknown."""
    facts = lookup.facts(oracle_id)
    return facts.name if facts is not None else str(oracle_id)
