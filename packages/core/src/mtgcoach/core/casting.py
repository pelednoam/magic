"""Casting a spell and letting it resolve.

Split from ``reduce`` at the line limit. The seam is a real one: these two are
the only events with a *gap* between them -- CR 601.2 is one action and so is
resolution, and the space between them is where answering a spell goes.

It is no longer an empty space. Casting takes priority to do (CR 117.1a) and
hands it straight back (CR 117.3c); resolution waits until every player has
passed in succession (CR 117.4), which is the moment the other player spends
deciding whether to answer. Before that the two arrived back to back, and a
player who wanted to respond had nowhere to do it.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from mtgcoach.core import priority
from mtgcoach.core import stack as stackzone
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.movement import add_card, remove_card
from mtgcoach.core.stack import StackObject
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

    Priority is checked first, before the card is even looked for. A player who
    may not act may not act, whatever they are holding (CR 117.1a), and telling
    somebody their card is not in their hand when the real answer is that this
    is not their moment teaches the wrong lesson.

    The spell goes on top of everything already there (CR 405.2), and the
    caster gets priority straight back (CR 117.3c) -- so they may hold a second
    trick, or pass and let it resolve.
    """
    priority.demanded(state, player_id)
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
    without, card = remove_card(paid, instance_id)
    on_stack = replace(
        state.with_player(player_id, without),
        stack=(*state.stack, StackObject(card, player_id)),
    )
    return priority.acted(on_stack, player_id)


def resolve(
    state: GameState, player_id: PlayerId, instance_id: InstanceId, to: ZoneName
) -> GameState:
    """Take the top spell off the stack, to where the rules send it.

    The top of *the* stack, not of the caster's half of it. Two spells filed
    under two players were two orders with no way to compare them, so the
    engine let the spell cast first resolve first -- the opposite of CR 405.5,
    and the opposite of what casting in response means (CR 117.7).

    And it resolves because every player passed in succession (CR 117.4,
    CR 608.1), not because its controller asked. The app asked, one event after
    casting, so the other player's window to answer closed before it opened.

    Raises:
        IllegalEventError: If the spell is not on the stack, is not on top, is
            not this player's to resolve, would resolve before everybody has
            passed, or is going somewhere a resolving spell cannot go. In that
            order, because that is the order a player wants to hear them.
    """
    found = stackzone.find(state.stack, instance_id)
    if found is None:
        msg = f"spell {instance_id!r} is not on the stack"
        raise IllegalEventError(msg)
    if stackzone.top(state.stack) is not found:
        # Identity, not equality: ``find`` hands back the object out of this
        # very tuple, so the two are the same object exactly when the spell is
        # on top. Comparing ids would have been the same answer by a longer
        # road, and re-checking for an empty stack one that cannot happen --
        # ``found`` is not None, so there is something on it.
        msg = f"spell {instance_id!r} is not the top of the stack"
        raise IllegalEventError(msg)
    if found.controller != player_id:
        msg = f"spell {instance_id!r} is {found.controller!r}'s, not {player_id!r}'s to resolve"
        raise IllegalEventError(msg)
    if not priority.all_passed(state):
        waiting = ", ".join(str(one) for one in priority.yet_to_pass(state))
        msg = f"spell {instance_id!r} does not resolve until {waiting} passes"
        raise IllegalEventError(msg)
    if to not in RESOLVES_TO:
        named = " or ".join(zone.value for zone in RESOLVES_TO)
        msg = f"a spell resolves to the {named}, not to the {to.value}"
        raise IllegalEventError(msg)
    landed = add_card(state.player(player_id), found.card, to, state.turn)
    return priority.resolved(replace(state.with_player(player_id, landed), stack=state.stack[:-1]))
