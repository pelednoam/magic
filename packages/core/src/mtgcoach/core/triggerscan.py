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

#: Triggers driven by something happening rather than by the clock. Listed so
#: that a new TriggerEvent has to be classified as one or the other rather than
#: silently never firing.
#:
#: ATTACKS, BLOCKS and DEALS_COMBAT_DAMAGE are here rather than under a step
#: because the step is only half their condition: the other half is having
#: attacked, blocked or connected, which this scanner cannot see.
EVENT_DRIVEN: Final[frozenset[TriggerEvent]] = frozenset(
    {
        TriggerEvent.ENTERS,
        TriggerEvent.DIES,
        TriggerEvent.ANOTHER_CREATURE_ENTERS,
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
    card with the latter is not reported on the opponent's turn. None is in the
    Beginner Box. Splitting the event is the fix, and it needs a re-extraction.
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


def every_event_is_classified() -> bool:
    """Whether each trigger event is either clock-driven or event-driven.

    Checked by a test rather than asserted at import: a new event that is
    neither would never fire and nothing would say so.
    """
    covered = set(AT_STEP.values()) | EVENT_DRIVEN
    return covered == set(TriggerEvent)
