"""Noticing triggers before they are missed."""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from helpers import MANA_ABILITY, UNKNOWN_ABILITY
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.effects import ChangeLife
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.steps import Step
from mtgcoach.core.targets import Controller
from mtgcoach.core.triggerscan import (
    AT_STEP,
    EVENT_DRIVEN,
    every_event_is_classified,
    triggers_at,
)
from mtgcoach.core.vocabulary import TriggerEvent

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.abilities import Ability

#: Any effect will do here; the scanner cares about the trigger, not the payload.
GAIN: Final[ChangeLife] = ChangeLife(1, Controller.YOU)

BOOK: dict[str, tuple[Ability, ...]] = {
    "Ajani's Pridemate": (TriggeredAbility(Trigger(TriggerEvent.YOU_GAIN_LIFE), (GAIN,)),),
    "Bloodthirsty Conqueror": (
        TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), (GAIN,)),
    ),
    "Goblin Raider": (TriggeredAbility(Trigger(TriggerEvent.ATTACKS), (GAIN,)),),
    "Nightshade Dryad": (TriggeredAbility(Trigger(TriggerEvent.END_STEP), (GAIN,)),),
    "Forest": (MANA_ABILITY,),
    "Puzzle": (UNKNOWN_ABILITY,),
}


def _abilities(oracle_id: OracleId) -> Sequence[Ability]:
    return BOOK.get(str(oracle_id), ())


def _names(oracle_id: OracleId) -> str:
    return str(oracle_id)


def _battlefield(*names: str) -> list[Permanent]:
    return [Permanent(CardInstance(InstanceId(f"{n}-1"), OracleId(n))).settle() for n in names]


def _scan(step: Step, *names: str) -> tuple[str, ...]:
    return tuple(r.name for r in triggers_at(step, _battlefield(*names), _abilities, _names))


def test_an_upkeep_trigger_is_reported_at_upkeep() -> None:
    assert _scan(Step.UPKEEP, "Bloodthirsty Conqueror") == ("Bloodthirsty Conqueror",)


def test_an_end_step_trigger_is_reported_at_the_end_step() -> None:
    assert _scan(Step.END_STEP, "Nightshade Dryad") == ("Nightshade Dryad",)


def test_a_trigger_is_not_reported_in_the_wrong_step() -> None:
    assert _scan(Step.UPKEEP, "Nightshade Dryad") == ()


def test_an_attack_trigger_is_not_reported_by_the_clock() -> None:
    """The scanner sees the battlefield, not the attackers.

    Reporting it at declare-attackers would remind you about every creature you
    own, including the ones that stayed home.
    """
    for step in Step:
        assert _scan(step, "Goblin Raider") == ()


def test_an_event_driven_trigger_is_never_reported_by_the_clock() -> None:
    """'Whenever you gain life' has no step; reporting it every turn is noise."""
    for step in Step:
        assert _scan(step, "Ajani's Pridemate") == ()


def test_a_step_with_no_triggers_of_its_own_reports_nothing() -> None:
    assert _scan(Step.UNTAP, "Bloodthirsty Conqueror") == ()


def test_activated_and_unmodelled_abilities_are_not_triggers() -> None:
    assert _scan(Step.UPKEEP, "Forest", "Puzzle") == ()


def test_a_card_the_fixture_does_not_know_is_skipped() -> None:
    assert _scan(Step.UPKEEP, "Unimported") == ()


def test_every_permanent_with_the_trigger_is_reported() -> None:
    battlefield = [
        Permanent(CardInstance(InstanceId(f"c{i}"), OracleId("Bloodthirsty Conqueror"))).settle()
        for i in range(3)
    ]
    found = triggers_at(Step.UPKEEP, battlefield, _abilities, _names)
    assert [r.instance_id for r in found] == [InstanceId(f"c{i}") for i in range(3)]


def test_a_reminder_carries_the_event_it_is_about() -> None:
    (reminder,) = triggers_at(
        Step.UPKEEP, _battlefield("Bloodthirsty Conqueror"), _abilities, _names
    )
    assert reminder.event is TriggerEvent.BEGINNING_OF_UPKEEP


def test_every_trigger_event_is_classified() -> None:
    """A new event that is neither clock- nor event-driven would never fire."""
    assert every_event_is_classified()


def test_the_two_classifications_do_not_overlap() -> None:
    assert not set(AT_STEP.values()) & EVENT_DRIVEN


def test_each_step_maps_to_a_distinct_event() -> None:
    assert len(set(AT_STEP.values())) == len(AT_STEP)
