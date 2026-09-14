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
    """CR 305.1: the card you play as a land has to be a land.

    An unmodelled card is allowed through. That is the same choice the coach
    makes everywhere else: at 52% of the box modelled, refusing what we cannot
    identify would make the tracker unusable, and the player can see their own
    card. Refusing what we *can* identify as not-a-land is the win here, because
    tapping a Grizzly Bears for mana is a mistake the tracker would otherwise
    keep for the rest of the game.
    """
    player = state.player(event.player)
    card = next((c for c in player.hand if c.instance_id == event.instance_id), None)
    if card is None:
        # The reducer will say this too, and better. Left to it.
        return
    facts = lookup.facts(card.oracle_id)
    if facts is not None and not facts.is_land:
        msg = f"{facts.name} is not a land"
        raise BadEventError(msg)
