"""Checks the engine cannot make for itself, made where the card data is.

``core`` is deliberately free of card data, and pays for it in one place: the
reducer cannot tell whether the card you are playing as your land is a land.
Its own docstring says so, and says the check "arrives with the card database".
This is where the card database arrives.

Everything here is a rule that needs to know what a card *is*. Anything that
needs only the state belongs in the reducer, where it cannot be skipped by a
caller who forgets to ask.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api.eventspec import BadEventError
from mtgcoach.core.events import PlayLand
from mtgcoach.core.legality import why_not_play_land

if TYPE_CHECKING:
    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState


def check(event: Event, state: GameState, lookup: CardLookup) -> None:
    """Refuse an event the card data says is illegal.

    Raises:
        BadEventError: If the event is one the cards involved do not allow.
    """
    if isinstance(event, PlayLand):
        _check_land(event, state, lookup)


def _check_land(event: PlayLand, state: GameState, lookup: CardLookup) -> None:
    """Refuse a land drop the coach has just said is illegal.

    Asks ``legality`` rather than re-deciding, which is the point. The first
    version checked only that the card was a land, and the reducer checks only
    hand membership and the land drop -- so nothing checked *timing*, and the
    server accepted a land played during the untap step while the advice in the
    very same response read "you can only play lands in a main phase". A server
    that contradicts its own coach is worse than one that is merely strict.

    An unmodelled card is still allowed through. That is the same choice the
    coach makes everywhere else: at 52% of the box modelled, refusing what we
    cannot identify would make the tracker unusable, and the player can see
    their own card.
    """
    player = state.player(event.player)
    card = next((c for c in player.hand if c.instance_id == event.instance_id), None)
    if card is None:
        # The reducer will say this too, and better. Left to it.
        return
    facts = lookup.facts(card.oracle_id)
    if facts is None:
        return
    reasons = why_not_play_land(state, event.player, facts)
    if reasons:
        msg = f"{facts.name}: {reasons[0]}"
        raise BadEventError(msg)
