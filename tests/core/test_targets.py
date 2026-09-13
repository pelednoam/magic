"""Target specs."""

from __future__ import annotations

from mtgcoach.core.targets import (
    ANY_CREATURE,
    Condition,
    Controller,
    TargetKind,
    TargetSpec,
)


def test_the_common_case_targets_any_creature() -> None:
    assert ANY_CREATURE.kinds == {TargetKind.CREATURE}
    assert ANY_CREATURE.controller is Controller.ANY
    assert ANY_CREATURE.conditions == frozenset()
    assert not ANY_CREATURE.is_optional


def test_up_to_one_target_is_optional() -> None:
    """`Prayer of Binding` exiles "up to one target nonland permanent"."""
    spec = TargetSpec(
        kinds=frozenset({TargetKind.PERMANENT}),
        controller=Controller.OPPONENT,
        conditions=frozenset({Condition.NONLAND}),
        minimum=0,
    )
    assert spec.is_optional


def test_a_required_target_is_not_optional() -> None:
    assert not TargetSpec(kinds=frozenset({TargetKind.SPELL})).is_optional


def test_several_kinds_at_once() -> None:
    """`Broken Wings` destroys an artifact, enchantment, or creature with flying."""
    spec = TargetSpec(
        kinds=frozenset({TargetKind.ARTIFACT, TargetKind.ENCHANTMENT, TargetKind.CREATURE}),
        conditions=frozenset({Condition.HAS_FLYING}),
    )
    assert len(spec.kinds) == 3
    assert Condition.HAS_FLYING in spec.conditions


def test_specs_with_the_same_content_are_equal() -> None:
    assert TargetSpec(kinds=frozenset({TargetKind.CREATURE})) == ANY_CREATURE
