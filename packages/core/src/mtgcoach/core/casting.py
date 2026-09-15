"""Casting a spell and letting it resolve.

Split from ``reduce`` at the line limit. The seam is a real one: these two are
the only events with a *gap* between them -- CR 601.2 is one action and so is
resolution, and the space between them is where answering a spell will go when
this engine has priority to hold.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.movement import move_card
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.ids import InstanceId, PlayerId
    from mtgcoach.core.state import GameState


#: Where a spell resolving normally can go: onto the battlefield if it is a
#: permanent spell (CR 608.3), into its owner's graveyard if it is an instant or
#: a sorcery (CR 608.2m). A spell that exiles itself does so as part of its own
#: effect, before 608.2m looks for it, and the engine models no card effects
#: yet -- so anything else here is a caller that is confused.
RESOLVES_TO = (ZoneName.BATTLEFIELD, ZoneName.GRAVEYARD)


def cast(
    state: GameState,
    player_id: PlayerId,
    instance_id: InstanceId,
    payment: Sequence[InstanceId],
) -> GameState:
    """Pay for a spell and put it on the stack, as one action (CR 601.2).

    All of it or none of it: every check happens before anything moves, so a
    refusal leaves the board exactly where it was. A player whose lands were
    tapped by a cast the server then refused would be worse off than one whose
    cast was simply refused.
    """
    player = state.player(player_id)
    if player.find(ZoneName.HAND, instance_id) is None:
        msg = f"card {instance_id!r} is not in {player_id!r}'s hand"
        raise IllegalEventError(msg)
    paid = player
    for source in payment:
        found = next((p for p in paid.battlefield if p.instance_id == source), None)
        if found is None:
            msg = f"no permanent {source!r} on {player_id!r}'s battlefield to pay with"
            raise IllegalEventError(msg)
        if found.tapped:
            # Also what catches the same land named twice: the second time
            # round it is tapped, because the first time tapped it.
            msg = f"{source!r} is already tapped, so it cannot pay for anything"
            raise IllegalEventError(msg)
        paid = replace(
            paid,
            battlefield=tuple(p.tap() if p.instance_id == source else p for p in paid.battlefield),
        )
    return state.with_player(player_id, move_card(paid, instance_id, ZoneName.STACK, state.turn))


def resolve(
    state: GameState, player_id: PlayerId, instance_id: InstanceId, to: ZoneName
) -> GameState:
    """Take the top spell off a player's stack, to where the rules send it.

    Raises:
        IllegalEventError: If the spell is not there, is not on top, or is
            going somewhere a resolving spell cannot go.
    """
    player = state.player(player_id)
    if player.find(ZoneName.STACK, instance_id) is None:
        msg = f"spell {instance_id!r} is not on {player_id!r}'s stack"
        raise IllegalEventError(msg)
    if player.stack[-1].instance_id != instance_id:
        # CR 608.1: the top object on the stack resolves, and the top is the
        # last one put there. Only within one player's stack, because that is
        # as much of the order as this engine keeps -- see ``ZoneName``. It is
        # never *wrong*, and it is strictly more than nothing.
        msg = f"spell {instance_id!r} is not the top of {player_id!r}'s stack"
        raise IllegalEventError(msg)
    if to not in RESOLVES_TO:
        named = " or ".join(zone.value for zone in RESOLVES_TO)
        msg = f"a spell resolves to the {named}, not to the {to.value}"
        raise IllegalEventError(msg)
    return state.with_player(player_id, move_card(player, instance_id, to, state.turn))
