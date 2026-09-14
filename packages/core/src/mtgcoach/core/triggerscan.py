"""Reminding you what is about to trigger.

Forgetting a trigger is the most common beginner mistake, and the one a coach
can fix most cheaply: the information is already on the battlefield, it just has
to be noticed at the right moment. So at every step boundary the battlefield is
walked for abilities whose condition the transition satisfies.

Only triggers the *clock alone* decides can be found this way, and that is a
shorter list than it first looks. "At the beginning of your upkeep" fires for
every permanent you control, so entering the upkeep is the whole condition. But
"whenever this creature attacks" fires only for a creature that actually
attacked, and this function is handed the battlefield, not the attackers -- it
would remind you about every creature you own, including the ones that stayed
home, which is noise dressed up as help.

So attacking, blocking, dealing combat damage, dying and gaining life are all
classified as event-driven: they are reported by whatever observes the event
(``combat`` knows who attacked; ``reduce`` knows what died), not by the clock.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mtgcoach.core.abilities import TriggeredAbility
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.ids import InstanceId, OracleId
    from mtgcoach.core.permanents import Permanent

#: Which step each clock-driven trigger fires in. Only the two whose condition
#: is the step itself, for every permanent on the battlefield.
AT_STEP: Final[dict[Step, TriggerEvent]] = {
    Step.UPKEEP: TriggerEvent.BEGINNING_OF_UPKEEP,
    Step.END_STEP: TriggerEvent.END_STEP,
}

#: Triggers whose event the *state* still remembers, so a scanner can find
#: them after the fact. A permanent that arrived since its controller's last
#: untap step is flagged ``summoning_sick``, and that flag is the record that
#: it entered -- so "when this enters" can be reported by looking at the
#: battlefield, which is the only reason these are not in ``EVENT_DRIVEN``.
#:
#: This split was found by self-play, not by a test. Sixty games reached zero
#: reminders, because the Beginner Box has 31 triggered abilities and every one
#: was classified event-driven -- so the panel could never fire for the set the
#: app is built for. These two are 24 of the 31.
ON_ARRIVAL: Final[frozenset[TriggerEvent]] = frozenset(
    {
        TriggerEvent.ENTERS,
        TriggerEvent.ANOTHER_CREATURE_ENTERS,
    }
)

#: Triggers driven by something happening that the state does not remember.
#: Listed so that a new TriggerEvent has to be classified rather than silently
#: never firing.
#:
#: ATTACKS, BLOCKS and DEALS_COMBAT_DAMAGE are here rather than under a step
#: because the step is only half their condition: the other half is having
#: attacked, blocked or connected, which this scanner cannot see. DIES,
#: YOU_GAIN_LIFE and YOU_CAST_SPELL are here because nothing on the board
#: afterwards says they happened.
EVENT_DRIVEN: Final[frozenset[TriggerEvent]] = frozenset(
    {
        TriggerEvent.DIES,
        TriggerEvent.YOU_GAIN_LIFE,
        TriggerEvent.YOU_CAST_SPELL,
        TriggerEvent.ATTACKS,
        TriggerEvent.BLOCKS,
        TriggerEvent.DEALS_COMBAT_DAMAGE,
    }
)


@dataclass(frozen=True, slots=True)
class Reminder:
    """A trigger the player is about to miss."""

    instance_id: InstanceId
    name: str
    event: TriggerEvent


def triggers_at(
    step: Step,
    battlefield: Sequence[Permanent],
    abilities: Callable[[OracleId], Sequence[Ability]],
    names: Callable[[OracleId], str],
    *,
    your_turn: bool,
) -> tuple[Reminder, ...]:
    """Every clock-driven trigger that fires on entering ``step``.

    ``abilities`` and ``names`` are lookups rather than data because ``core``
    holds no card data; the caller supplies them from the sealed fixture.

    ``your_turn`` is required rather than defaulted because the step is only
    half the condition: "at the beginning of **your** upkeep" needs to be your
    upkeep, and without it these reminders fired twice a round -- on your turn
    and on the opponent's.

    A known gap, stated because it is a gap and not a decision: the schema's
    ``TriggerEvent`` does not distinguish "your upkeep" from "each upkeep", so a
    card with the latter is not reported on the opponent's turn. The same
    applies to the end step, and applies harder -- "at the beginning of the end
    step" is the commoner printing of the two, so this is where the gap will
    first cost something. Neither is in the Beginner Box. Splitting the event is
    the fix, and it needs a re-extraction.
    """
    event = AT_STEP.get(step)
    if event is None or not your_turn:
        return ()
    return tuple(
        Reminder(permanent.instance_id, names(permanent.card.oracle_id), event)
        for permanent in battlefield
        for ability in abilities(permanent.card.oracle_id)
        if isinstance(ability, TriggeredAbility) and ability.trigger.event is event
    )


def arrivals(
    battlefield: Sequence[Permanent],
    abilities: Callable[[OracleId], Sequence[Ability]],
    names: Callable[[OracleId], str],
) -> tuple[Reminder, ...]:
    """Every arrival trigger on a permanent that has recently arrived.

    Two shapes, and they are not the same permanent:

    - **"When this enters"** -- the permanent with the ability is the one that
      arrived, so it is reported when it is itself newly here.
    - **"Whenever another creature enters"** -- the ability is on a permanent
      that was already here, and something *else* arriving is what fired it. So
      it is reported when any other permanent is newly here.

    **The window is "since your last untap step", not "this turn"**, because
    ``summoning_sick`` is the only record the state keeps of having arrived.
    That is wider than the moment the trigger fired: a creature played on your
    turn is still flagged through the opponent's. For a tracker somebody is
    filling in by hand that is the better error to make -- the reminder stays
    up until the turn comes back round, rather than flashing past in one step
    and being missed. A narrower window wants ``entered_on_turn`` on
    ``Permanent``, which is a state-model change and a bigger one than this.

    Unlike ``triggers_at`` this takes no ``your_turn``: a permanent can arrive
    on either player's turn, and whose turn it is says nothing about whether
    its arrival trigger was resolved.
    """
    arrived = [permanent for permanent in battlefield if permanent.summoning_sick]
    if not arrived:
        return ()
    fresh = {permanent.instance_id for permanent in arrived}
    return tuple(
        Reminder(permanent.instance_id, names(permanent.card.oracle_id), ability.trigger.event)
        for permanent in battlefield
        for ability in abilities(permanent.card.oracle_id)
        if isinstance(ability, TriggeredAbility)
        if _arrived_for(ability.trigger.event, permanent.instance_id, fresh)
    )


def _arrived_for(event: TriggerEvent, instance_id: InstanceId, fresh: set[InstanceId]) -> bool:
    """Whether this arrival trigger has something to fire on."""
    if event is TriggerEvent.ENTERS:
        return instance_id in fresh
    if event is TriggerEvent.ANOTHER_CREATURE_ENTERS:
        return bool(fresh - {instance_id})
    return False


def every_event_is_classified() -> bool:
    """Whether each trigger event is clock-, arrival- or event-driven.

    Checked by a test rather than asserted at import: a new event that is none
    of them would never fire and nothing would say so. That is not a
    hypothetical -- every trigger in the Beginner Box sat in ``EVENT_DRIVEN``,
    which this function was perfectly happy with, and the panel was dead for
    two milestones before a self-play season counted how often it fired.
    """
    covered = set(AT_STEP.values()) | ON_ARRIVAL | EVENT_DRIVEN
    return covered == set(TriggerEvent) and not (ON_ARRIVAL & EVENT_DRIVEN)
