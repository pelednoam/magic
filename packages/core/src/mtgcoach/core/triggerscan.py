"""Reminding you what is about to trigger.

Forgetting a trigger is the most common beginner mistake, and the one a coach
can fix most cheaply: the information is already on the battlefield, it just has
to be noticed at the right moment. So at every step boundary the battlefield is
walked for abilities whose condition the transition satisfies.

Only step-driven triggers can be found this way. "When this creature dies" and
"whenever you gain life" are driven by events, not by the clock, and they are
reported when the event happens rather than when a step begins.
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

#: Which step each clock-driven trigger fires in.
AT_STEP: Final[dict[Step, TriggerEvent]] = {
    Step.UPKEEP: TriggerEvent.BEGINNING_OF_UPKEEP,
    Step.DECLARE_ATTACKERS: TriggerEvent.ATTACKS,
    Step.DECLARE_BLOCKERS: TriggerEvent.BLOCKS,
    Step.COMBAT_DAMAGE: TriggerEvent.DEALS_COMBAT_DAMAGE,
    Step.END_STEP: TriggerEvent.END_STEP,
}

#: Triggers driven by something happening rather than by the clock. Listed so
#: that a new TriggerEvent has to be classified as one or the other rather than
#: silently never firing.
EVENT_DRIVEN: Final[frozenset[TriggerEvent]] = frozenset(
    {
        TriggerEvent.ENTERS,
        TriggerEvent.DIES,
        TriggerEvent.ANOTHER_CREATURE_ENTERS,
        TriggerEvent.YOU_GAIN_LIFE,
        TriggerEvent.YOU_CAST_SPELL,
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
) -> tuple[Reminder, ...]:
    """Every clock-driven trigger that fires on entering ``step``.

    ``abilities`` and ``names`` are lookups rather than data because ``core``
    holds no card data; the caller supplies them from the sealed fixture.
    """
    event = AT_STEP.get(step)
    if event is None:
        return ()
    return tuple(
        Reminder(permanent.instance_id, names(permanent.card.oracle_id), event)
        for permanent in battlefield
        for ability in abilities(permanent.card.oracle_id)
        if isinstance(ability, TriggeredAbility) and ability.trigger.event is event
    )


def every_event_is_classified() -> bool:
    """Whether each trigger event is either clock-driven or event-driven.

    Checked by a test rather than asserted at import: a new event that is
    neither would never fire and nothing would say so.
    """
    covered = set(AT_STEP.values()) | EVENT_DRIVEN
    return covered == set(TriggerEvent)
