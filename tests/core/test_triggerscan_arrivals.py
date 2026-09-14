"""Triggers the state still remembers, because the permanent is newly here.

Split from `test_triggerscan`, which covers the clock-driven half. These are
the other question: what fired when something came onto the battlefield, found
by looking for permanents that are still flagged summoning-sick.

The whole class existed and fired for nobody. Every one of the Beginner Box's
31 triggered abilities was classified event-driven, so the panel could never
report any of them -- for two milestones, and no test said so, because every
test that existed was about the clock. A self-play season counting how often
the panel fired is what noticed.
"""

from __future__ import annotations

from dataclasses import replace

from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.triggerscan import arrivals
from mtgcoach.core.vocabulary import TriggerEvent


def _permanent(name: str) -> Permanent:
    """One permanent, settled, for an arrival test to un-settle."""
    return Permanent(CardInstance(InstanceId(f"{name}-1"), OracleId(name))).settle()


def test_an_arrival_trigger_fires_for_the_permanent_that_arrived() -> None:
    """The panel was dead for two milestones and nothing said so.

    The Beginner Box has 31 triggered abilities and every one was classified
    event-driven, so `triggers_at` could never report any of them -- and a
    self-play season counting how often the panel fired is what noticed.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    fresh = replace(_permanent("Elite"), summoning_sick=True)
    found = arrivals((fresh,), lambda _o: (entering,), lambda _o: "Elite")
    assert [r.name for r in found] == ["Elite"]


def test_an_arrival_trigger_does_not_fire_once_it_has_settled() -> None:
    """A permanent that has been here since your turn began did not just arrive.

    So nothing of its is outstanding.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    settled = replace(_permanent("Elite"), summoning_sick=False)
    assert arrivals((settled,), lambda _o: (entering,), lambda _o: "Elite") == ()


def test_another_creature_entering_fires_the_watcher_not_the_newcomer() -> None:
    """The two shapes are not the same permanent.

    "Whenever another creature enters" sits on something that was already
    here; the arrival that fires it is somebody else's.
    """
    watching = TriggeredAbility(Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS), ())
    watcher = replace(_permanent("Watcher"), summoning_sick=False)
    newcomer = replace(_permanent("Newcomer"), summoning_sick=True)
    found = arrivals(
        (watcher, newcomer),
        lambda oracle: (watching,) if str(oracle) == "Watcher" else (),
        str,
    )
    assert [r.name for r in found] == ["Watcher"]


def test_another_creature_entering_does_not_fire_on_its_own_arrival() -> None:
    """*Another* creature. A lone newcomer with the ability triggers nothing."""
    watching = TriggeredAbility(Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS), ())
    alone = replace(_permanent("Watcher"), summoning_sick=True)
    assert arrivals((alone,), lambda _o: (watching,), str) == ()


def test_a_board_where_nothing_arrived_is_not_walked() -> None:
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    settled = replace(_permanent("Elite"), summoning_sick=False)
    assert arrivals((settled, settled), lambda _o: (entering,), str) == ()


def test_a_clock_trigger_is_not_reported_as_an_arrival() -> None:
    """Each scanner answers its own question; overlapping would double-report."""
    upkeep = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())
    fresh = replace(_permanent("Bell"), summoning_sick=True)
    assert arrivals((fresh,), lambda _o: (upkeep,), str) == ()
