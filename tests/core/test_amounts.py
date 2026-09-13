"""Fixed and dynamic amounts."""

from __future__ import annotations

from mtgcoach.core.amounts import Dynamic, Quantity


def test_a_dynamic_amount_names_what_to_look_up() -> None:
    """`Bite Down` deals damage equal to its power; a number cannot say that."""
    amount = Dynamic(Quantity.SOURCE_POWER)
    assert amount.quantity is Quantity.SOURCE_POWER


def test_dynamic_amounts_compare_by_value() -> None:
    assert Dynamic(Quantity.X) == Dynamic(Quantity.X)
    assert Dynamic(Quantity.X) != Dynamic(Quantity.SOURCE_POWER)


def test_every_quantity_has_a_stable_name() -> None:
    """The names are written into sealed fixtures, so they cannot drift."""
    assert {q.value for q in Quantity} == {
        "source_power",
        "source_toughness",
        "target_power",
        "x",
    }
