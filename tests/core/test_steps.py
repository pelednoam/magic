"""Turn structure invariants."""

from __future__ import annotations

from hypothesis import given
from hypothesis import strategies as st

from mtgcoach.core.steps import TURN_ORDER, Step, is_combat, is_main_phase, next_step

steps = st.sampled_from(list(Step))


def test_turn_order_covers_every_step_exactly_once() -> None:
    """Adding a Step without placing it in TURN_ORDER must fail the suite."""
    assert set(TURN_ORDER) == set(Step)
    assert len(TURN_ORDER) == len(Step)


@given(steps)
def test_a_full_cycle_returns_to_the_same_step(step: Step) -> None:
    current = step
    for _ in range(len(TURN_ORDER)):
        current = next_step(current)
    assert current == step


@given(steps)
def test_next_step_always_advances(step: Step) -> None:
    assert next_step(step) != step


def test_cleanup_wraps_to_untap() -> None:
    assert next_step(Step.CLEANUP) == Step.UNTAP


def test_steps_follow_the_comprehensive_rules_order() -> None:
    assert next_step(Step.UNTAP) == Step.UPKEEP
    assert next_step(Step.DRAW) == Step.PRECOMBAT_MAIN
    assert next_step(Step.DECLARE_ATTACKERS) == Step.DECLARE_BLOCKERS
    assert next_step(Step.END_COMBAT) == Step.POSTCOMBAT_MAIN


def test_main_phases() -> None:
    assert is_main_phase(Step.PRECOMBAT_MAIN)
    assert is_main_phase(Step.POSTCOMBAT_MAIN)
    assert not is_main_phase(Step.UPKEEP)
    assert not is_main_phase(Step.DECLARE_ATTACKERS)


def test_combat_steps() -> None:
    assert is_combat(Step.BEGIN_COMBAT)
    assert is_combat(Step.COMBAT_DAMAGE)
    assert is_combat(Step.END_COMBAT)
    assert not is_combat(Step.PRECOMBAT_MAIN)
    assert not is_combat(Step.CLEANUP)


@given(steps)
def test_a_step_is_never_both_main_phase_and_combat(step: Step) -> None:
    assert not (is_main_phase(step) and is_combat(step))
