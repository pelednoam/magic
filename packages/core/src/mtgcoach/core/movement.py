"""Moving a card between one player's zones.

Every movement is remove-then-add, so the number of cards a player owns cannot
change no matter which event moved them. That is what makes the conservation
property in the test suite a real invariant rather than a hopeful assertion.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, assert_never

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import InstanceId
    from mtgcoach.core.player import PlayerState


def _split(
    cards: tuple[CardInstance, ...], instance_id: InstanceId
) -> tuple[CardInstance, tuple[CardInstance, ...]]:
    """Return the named card and the rest, order preserved."""
    taken = next(c for c in cards if c.instance_id == instance_id)
    kept = tuple(c for c in cards if c.instance_id != instance_id)
    return taken, kept


def _remove_from(
    player: PlayerState, zone: ZoneName, instance_id: InstanceId
) -> tuple[PlayerState, CardInstance]:
    """Remove a card known to be in ``zone``.

    Written out per zone rather than assigning through a computed field name:
    the explicit form is what lets both type checkers verify that every zone is
    handled and that each one is assigned a value of the right type.
    """
    match zone:
        case ZoneName.BATTLEFIELD:
            taken = next(p for p in player.battlefield if p.instance_id == instance_id)
            kept = tuple(p for p in player.battlefield if p.instance_id != instance_id)
            return replace(player, battlefield=kept), taken.card
        case ZoneName.LIBRARY:
            card, rest = _split(player.library, instance_id)
            return replace(player, library=rest), card
        case ZoneName.HAND:
            card, rest = _split(player.hand, instance_id)
            return replace(player, hand=rest), card
        case ZoneName.GRAVEYARD:
            card, rest = _split(player.graveyard, instance_id)
            return replace(player, graveyard=rest), card
        case ZoneName.EXILE:
            card, rest = _split(player.exile, instance_id)
            return replace(player, exile=rest), card
    assert_never(zone)


def remove_card(player: PlayerState, instance_id: InstanceId) -> tuple[PlayerState, CardInstance]:
    """Take one card out of whichever zone holds it.

    Raises:
        IllegalEventError: If the player owns no such card.
    """
    for zone in ZoneName:
        if player.find(zone, instance_id) is not None:
            return _remove_from(player, zone, instance_id)
    msg = f"no card {instance_id!r} in any zone"
    raise IllegalEventError(msg)


def add_card(player: PlayerState, card: CardInstance, zone: ZoneName) -> PlayerState:
    """Put a card into a zone.

    A card entering the battlefield is summoning sick, which is true of every
    permanent and only *matters* for creatures -- the distinction belongs to the
    legality rules, not to the state.
    """
    match zone:
        case ZoneName.BATTLEFIELD:
            return replace(player, battlefield=(*player.battlefield, Permanent(card)))
        case ZoneName.LIBRARY:
            return replace(player, library=(*player.library, card))
        case ZoneName.HAND:
            return replace(player, hand=(*player.hand, card))
        case ZoneName.GRAVEYARD:
            return replace(player, graveyard=(*player.graveyard, card))
        case ZoneName.EXILE:
            return replace(player, exile=(*player.exile, card))
    assert_never(zone)


def move_card(player: PlayerState, instance_id: InstanceId, to: ZoneName) -> PlayerState:
    """Move one card to ``to``, wherever it currently is."""
    without, card = remove_card(player, instance_id)
    return add_card(without, card, to)
