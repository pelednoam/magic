"""Applying an event to a state.

The single place where the game changes. Every transition is a pure function of
``(state, event)``, so a game is exactly its starting position plus its event
log -- the property the test suite checks by replaying every log it generates.

The ``match`` is closed with ``assert_never``: a new member of ``Event`` fails
the type check here until it is handled.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, assert_never

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import (
    AdvanceStep,
    CastSpell,
    ChangeLife,
    DrawCard,
    MoveCard,
    PlayLand,
    ResolveSpell,
    SetTapped,
)
from mtgcoach.core.movement import move_card
from mtgcoach.core.player import MAX_LAND_DROPS_PER_TURN
from mtgcoach.core.turn import advance, draw_card
from mtgcoach.core.zones import ZoneName

#: The events that take a card from one zone to another. Named so that both
#: ``apply`` and ``_moved`` can be closed over their own halves of ``Event``.
type Moving = PlayLand | CastSpell | ResolveSpell | MoveCard

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mtgcoach.core.events import Event
    from mtgcoach.core.ids import InstanceId, PlayerId
    from mtgcoach.core.state import GameState


def apply(state: GameState, event: Event) -> GameState:
    """Return the state that results from applying ``event``.

    Raises:
        IllegalEventError: If the event cannot legally be applied.
    """
    match event:
        case AdvanceStep():
            return advance(state)
        case DrawCard(player=player_id):
            return draw_card(state, player_id)
        case PlayLand() | CastSpell() | ResolveSpell() | MoveCard():
            return _moved(state, event)
        case SetTapped(player=player_id, instance_id=instance_id, tapped=tapped):
            return _set_tapped(state, player_id, instance_id, tapped=tapped)
        case ChangeLife(player=player_id, amount=amount):
            player = state.player(player_id)
            return state.with_player(player_id, replace(player, life=player.life + amount))
    assert_never(event)


def _moved(state: GameState, event: Moving) -> GameState:
    """The events that take a card from one zone to another.

    A second closed match rather than four more arms on the first, which had
    grown past what one function may branch on. Both ends stay honest: this one
    is ``assert_never``-closed over ``Moving`` and the caller is
    ``assert_never``-closed over ``Event``, so a new event is a type error at
    one of the two until somebody decides which it is.

    Raises:
        IllegalEventError: If the move is not a legal one.
    """
    match event:
        case PlayLand(player=player_id, instance_id=instance_id):
            return _play_land(state, player_id, instance_id)
        case CastSpell(player=player_id, instance_id=instance_id):
            return _cast(state, player_id, instance_id)
        case ResolveSpell(player=player_id, instance_id=instance_id, to=zone):
            return _resolve(state, player_id, instance_id, zone)
        case MoveCard(player=player_id, instance_id=instance_id, to=zone):
            player = state.player(player_id)
            return state.with_player(player_id, move_card(player, instance_id, zone, state.turn))
    assert_never(event)


def replay(initial: GameState, events: Iterable[Event]) -> GameState:
    """Fold an event log over a starting position.

    ``replay(initial, log)`` equals the state reached by applying the log one
    event at a time -- trivially true here, and asserted as a property so that
    it stays true as the reducer grows.
    """
    state = initial
    for event in events:
        state = apply(state, event)
    return state


def _play_land(state: GameState, player_id: PlayerId, instance_id: InstanceId) -> GameState:
    player = state.player(player_id)
    if player.find(ZoneName.HAND, instance_id) is None:
        msg = f"card {instance_id!r} is not in {player_id!r}'s hand"
        raise IllegalEventError(msg)
    if player.lands_played_this_turn >= MAX_LAND_DROPS_PER_TURN:
        msg = f"{player_id!r} has already played a land this turn"
        raise IllegalEventError(msg)
    played = move_card(player, instance_id, ZoneName.BATTLEFIELD, state.turn)
    return state.with_player(
        player_id,
        replace(played, lands_played_this_turn=player.lands_played_this_turn + 1),
    )


#: Where a spell resolving normally can go: onto the battlefield if it is a
#: permanent spell (CR 608.3), into its owner's graveyard if it is an instant or
#: a sorcery (CR 608.2m). A spell that exiles itself does so as part of its own
#: effect, before 608.2m looks for it, and the engine models no card effects
#: yet -- so anything else here is a caller that is confused.
RESOLVES_TO = (ZoneName.BATTLEFIELD, ZoneName.GRAVEYARD)


def _cast(state: GameState, player_id: PlayerId, instance_id: InstanceId) -> GameState:
    player = state.player(player_id)
    if player.find(ZoneName.HAND, instance_id) is None:
        msg = f"card {instance_id!r} is not in {player_id!r}'s hand"
        raise IllegalEventError(msg)
    return state.with_player(player_id, move_card(player, instance_id, ZoneName.STACK, state.turn))


def _resolve(
    state: GameState, player_id: PlayerId, instance_id: InstanceId, to: ZoneName
) -> GameState:
    player = state.player(player_id)
    if player.find(ZoneName.STACK, instance_id) is None:
        msg = f"spell {instance_id!r} is not on {player_id!r}'s stack"
        raise IllegalEventError(msg)
    if to not in RESOLVES_TO:
        named = " or ".join(zone.value for zone in RESOLVES_TO)
        msg = f"a spell resolves to the {named}, not to the {to.value}"
        raise IllegalEventError(msg)
    return state.with_player(player_id, move_card(player, instance_id, to, state.turn))


def _set_tapped(
    state: GameState,
    player_id: PlayerId,
    instance_id: InstanceId,
    *,
    tapped: bool,
) -> GameState:
    player = state.player(player_id)
    if player.find(ZoneName.BATTLEFIELD, instance_id) is None:
        msg = f"no permanent {instance_id!r} on {player_id!r}'s battlefield"
        raise IllegalEventError(msg)
    battlefield = tuple(
        (p.tap() if tapped else p.untap()) if p.instance_id == instance_id else p
        for p in player.battlefield
    )
    return state.with_player(player_id, replace(player, battlefield=battlefield))
