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
        case ZoneName.STACK:
            card, rest = _split(player.stack, instance_id)
            return replace(player, stack=rest), card
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


def add_card(player: PlayerState, card: CardInstance, zone: ZoneName, turn: int = 0) -> PlayerState:
    """Put a card into a zone.

    A card entering the battlefield is summoning sick, which is true of every
    permanent and only *matters* for creatures -- the distinction belongs to the
    legality rules, not to the state.

    ``turn`` is recorded on the permanent because an "enters" trigger fires at
    the moment it arrives, and nothing else in the state says when that was.
    Defaulted so that a caller building a board by hand does not have to
    invent one; a real move always passes it.
    """
    match zone:
        case ZoneName.BATTLEFIELD:
            arrived = Permanent(card, entered_on_turn=turn)
            return replace(player, battlefield=(*player.battlefield, arrived))
        case ZoneName.LIBRARY:
            return replace(player, library=(*player.library, card))
        case ZoneName.HAND:
            return replace(player, hand=(*player.hand, card))
        case ZoneName.STACK:
            return replace(player, stack=(*player.stack, card))
        case ZoneName.GRAVEYARD:
            return replace(player, graveyard=(*player.graveyard, card))
        case ZoneName.EXILE:
            return replace(player, exile=(*player.exile, card))
    assert_never(zone)


def move_card(
    player: PlayerState, instance_id: InstanceId, to: ZoneName, turn: int = 0
) -> PlayerState:
    """Move one card to ``to``, wherever it currently is.

    ``turn`` is passed through to ``add_card`` so a permanent knows when it
    arrived; see there for why the state has to remember.

    Raises:
        IllegalEventError: If the card is already in ``to``. Remove-then-add
            would rebuild it -- silently untapping a permanent and making it
            summoning sick again -- and a caller asking for a move that is not
            a move is confused rather than expressing something meaningful.
    """
    if player.find(to, instance_id) is not None:
        msg = f"card {instance_id!r} is already in {to}"
        raise IllegalEventError(msg)
    without, card = remove_card(player, instance_id)
    return add_card(without, card, to, turn)
