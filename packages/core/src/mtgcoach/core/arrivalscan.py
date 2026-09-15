"""Triggers that fired because something came onto the battlefield.

The other half of ``triggerscan``, split from it at the line limit. That module
asks what the *clock* fires on entering a step; this asks what fired when a
permanent arrived. Different questions with different answers, and the panel is
empty for most real boards without both -- the Beginner Box has no clock-driven
trigger at all.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.abilities import TriggeredAbility
from mtgcoach.core.triggerscan import Reminder
from mtgcoach.core.vocabulary import TriggerEvent

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.ids import InstanceId, OracleId
    from mtgcoach.core.permanents import Permanent


def arrivals(
    battlefield: Sequence[Permanent],
    abilities: Callable[[OracleId], Sequence[Ability]],
    names: Callable[[OracleId], str],
    turn: int,
    is_creature: Callable[[OracleId], bool],
) -> tuple[Reminder, ...]:
    """Every arrival trigger that fired *this turn*.

    Two shapes, and they are not the same permanent:

    - **"When this enters"** -- the permanent with the ability is the one that
      arrived, so it is reported when it is itself newly here.
    - **"Whenever another creature enters"** -- the ability is on a permanent
      that was already here, and something *else* arriving is what fired it. So
      it is reported when any other permanent arrived this turn.

    **Exactly this turn.** The first version used ``summoning_sick``, which is
    cleared at the controller's untap step rather than at end of turn -- so a
    creature played on your turn was still flagged through the opponent's, and
    the panel claimed a trigger had fired when it had fired a turn ago. That is
    a reminder teaching something false, which is worse than no reminder. The
    permanent records the turn it arrived on and this compares it.

    **A creature, for the creature trigger.** ``is_creature`` is asked about
    each permanent that arrived, because "whenever another *creature* enters"
    says creature and a land is not one. Without it a Forest coming down fired
    every Dazzling Angel on the table -- a reminder to apply an ability that
    did not trigger, which is the same "teaching something false" failure as
    the turn bug above and is worse than an empty panel. ``core`` holds no card
    data, so the question is asked of the caller, exactly as ``names`` is.

    Unlike ``triggers_at`` this takes no ``your_turn``: a permanent can arrive
    on either player's turn, and whose turn it is says nothing about whether
    its arrival trigger fired.
    """
    arrived = [one for one in battlefield if one.entered_on_turn == turn]
    if not arrived:
        return ()
    fresh = {one.instance_id for one in arrived}
    creatures = {one.instance_id for one in arrived if is_creature(one.card.oracle_id)}
    return tuple(
        Reminder(permanent.instance_id, names(permanent.card.oracle_id), ability.trigger.event)
        for permanent in battlefield
        for ability in abilities(permanent.card.oracle_id)
        if isinstance(ability, TriggeredAbility)
        if _arrived_for(ability.trigger.event, permanent.instance_id, fresh, creatures)
    )


def _arrived_for(
    event: TriggerEvent,
    instance_id: InstanceId,
    fresh: set[InstanceId],
    creatures: set[InstanceId],
) -> bool:
    """Whether this arrival trigger has something to fire on.

    ``fresh`` is everything that arrived this turn; ``creatures`` is the part
    of it that is a creature. The two are different sets and the difference is
    the whole point -- a land entering is an arrival and is not a creature
    entering.
    """
    if event is TriggerEvent.ENTERS:
        return instance_id in fresh
    if event is TriggerEvent.ANOTHER_CREATURE_ENTERS:
        return bool(creatures - {instance_id})
    return False
