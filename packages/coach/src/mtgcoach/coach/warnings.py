"""Both kinds of trigger a player is about to miss.

Split from ``report`` because it is two scanners with one answer, and the
reason there are two is worth a file of its own: ``triggers_at`` asks what the
*clock* fires on entering this step, ``arrivals`` asks what fired when
something came onto the battlefield. Either alone is a panel that is empty for
most real boards -- the Beginner Box has no clock-driven trigger at all, so
this returned nothing for two milestones and a self-play season is what
noticed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.arrivalscan import arrivals
from mtgcoach.core.triggerscan import triggers_at

if TYPE_CHECKING:
    from collections.abc import Callable

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.ids import OracleId
    from mtgcoach.core.player import PlayerState
    from mtgcoach.core.state import GameState
    from mtgcoach.core.triggerscan import Reminder


def reminders(
    state: GameState,
    player: PlayerState,
    lookup: CardLookup,
    named: Callable[[OracleId], str],
    *,
    your_turn: bool,
) -> tuple[Reminder, ...]:
    """Every trigger this player is about to miss, of both kinds it can know.

    Two scanners rather than one because the questions differ. ``triggers_at``
    asks what the *clock* fires on entering this step; ``arrivals`` asks what
    fired when something came onto the battlefield, which the state still
    remembers because a new permanent is flagged summoning-sick.

    Both, because either alone is a panel that is empty for most real boards --
    the Beginner Box has no clock-driven trigger at all, so this returned
    nothing for two milestones and a self-play season is what noticed.
    """
    return (
        *triggers_at(state.step, player.battlefield, lookup.abilities, named, your_turn=your_turn),
        *arrivals(
            player.battlefield,
            lookup.abilities,
            named,
            state.turn,
            lambda oracle_id: _is_creature(lookup, oracle_id),
        ),
    )


def _is_creature(lookup: CardLookup, oracle_id: OracleId) -> bool:
    """Whether this card is a creature, for the "another creature" trigger.

    A card the coach cannot identify is not a creature here. That is the safe
    side: an unknown permanent entering will not fire somebody's Dazzling
    Angel, and the cards it cannot speak for are already listed separately as
    cards it cannot speak for.
    """
    facts = lookup.facts(oracle_id)
    return facts is not None and facts.is_creature
