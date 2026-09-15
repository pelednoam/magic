"""Triggers the state still remembers, because the permanent is newly here.

Split from `test_triggerscan`, which covers the clock-driven half. These are
the other question: what fired when something came onto the battlefield, found
by comparing the turn each permanent arrived on with the turn it is now.

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

#: The turn every test below is on.
NOW = 4


def _permanent(name: str, arrived: int = 0) -> Permanent:
    """One permanent, which arrived on ``arrived`` -- 0 meaning "was here"."""
    card = CardInstance(InstanceId(f"{name}-1"), OracleId(name))
    return Permanent(card, entered_on_turn=arrived).settle()


def test_an_arrival_trigger_fires_for_the_permanent_that_arrived() -> None:
    """The panel was dead for two milestones and nothing said so.

    The Beginner Box has 31 triggered abilities and every one was classified
    event-driven, so `triggers_at` could never report any of them -- and a
    self-play season counting how often the panel fired is what noticed.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    fresh = _permanent("Elite", arrived=NOW)
    found = arrivals((fresh,), lambda _o: (entering,), lambda _o: "Elite", NOW)
    assert [r.name for r in found] == ["Elite"]


def test_an_arrival_trigger_stops_firing_when_the_turn_ends() -> None:
    """Exactly this turn, and this is the reason the state records one.

    The first version used `summoning_sick`, which is cleared at the
    controller's *untap* -- so a creature played on your turn stayed flagged
    through the opponent's, and the panel said a trigger had fired when it had
    fired a turn ago. A reminder teaching something false is worse than none.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    yesterday = _permanent("Elite", arrived=NOW - 1)
    assert arrivals((yesterday,), lambda _o: (entering,), lambda _o: "Elite", NOW) == ()


def test_a_permanent_still_summoning_sick_from_last_turn_does_not_fire() -> None:
    """The exact case the old window got wrong.

    Played on your turn, so it is still sick through the opponent's -- and its
    enters trigger fired a turn ago, not now.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    sick = replace(_permanent("Elite", arrived=NOW - 1), summoning_sick=True)
    assert arrivals((sick,), lambda _o: (entering,), lambda _o: "Elite", NOW) == ()


def test_a_board_written_out_by_hand_never_reads_as_just_arrived() -> None:
    """A default of 0, and turns start at 1.

    So a fixture board -- or one somebody typed in -- cannot fire an arrival
    trigger by accident.
    """
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    assert arrivals((_permanent("Elite"),), lambda _o: (entering,), lambda _o: "Elite", 1) == ()


def test_another_creature_entering_fires_the_watcher_not_the_newcomer() -> None:
    """The two shapes are not the same permanent.

    "Whenever another creature enters" sits on something that was already
    here; the arrival that fires it is somebody else's.
    """
    watching = TriggeredAbility(Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS), ())
    watcher = _permanent("Watcher", arrived=NOW - 2)
    newcomer = _permanent("Newcomer", arrived=NOW)
    found = arrivals(
        (watcher, newcomer),
        lambda oracle: (watching,) if str(oracle) == "Watcher" else (),
        str,
        NOW,
    )
    assert [r.name for r in found] == ["Watcher"]


def test_another_creature_entering_does_not_fire_on_its_own_arrival() -> None:
    """*Another* creature. A lone newcomer with the ability triggers nothing."""
    watching = TriggeredAbility(Trigger(TriggerEvent.ANOTHER_CREATURE_ENTERS), ())
    alone = _permanent("Watcher", arrived=NOW)
    assert arrivals((alone,), lambda _o: (watching,), str, NOW) == ()


def test_a_board_where_nothing_arrived_is_not_walked() -> None:
    entering = TriggeredAbility(Trigger(TriggerEvent.ENTERS), ())
    old = _permanent("Elite", arrived=NOW - 3)
    assert arrivals((old, old), lambda _o: (entering,), str, NOW) == ()


def test_a_clock_trigger_is_not_reported_as_an_arrival() -> None:
    """Each scanner answers its own question; overlapping would double-report."""
    upkeep = TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ())
    fresh = _permanent("Bell", arrived=NOW)
    assert arrivals((fresh,), lambda _o: (upkeep,), str, NOW) == ()
