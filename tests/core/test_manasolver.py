"""Paying a cost, and which sources to keep.

The properties here are checked against a deliberately slow reference: a
brute-force search over every subset and every permutation, obviously correct
and far too slow to ship. If the two ever disagree, one of them is wrong and the
test says which inputs found it.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mtgcoach.core.ids import InstanceId
from mtgcoach.core.manacost import ManaCost, ManaSource, parse
from mtgcoach.core.manasolver import can_pay, payments

if TYPE_CHECKING:
    from collections.abc import Sequence

COLORS = "WUBRG"


def land(name: str, colors: str) -> ManaSource:
    return ManaSource(InstanceId(name), frozenset(colors))


BOARD = [
    land("forest-1", "G"),
    land("forest-2", "G"),
    land("island", "U"),
    land("mountain", "R"),
    land("elves", "G"),
]


# --- the slow reference ----------------------------------------------------


def _reference_can_pay(cost: ManaCost, sources: Sequence[ManaSource]) -> bool:
    """Try every subset, and every way of assigning it. Obviously correct."""
    if cost.colorless:
        return False
    need = cost.total
    for chosen in itertools.combinations(range(len(sources)), need):
        for order in itertools.permutations(chosen):
            coloured = order[: len(cost.symbols)]
            if all(
                sources[i].can_pay(symbol) for i, symbol in zip(coloured, cost.symbols, strict=True)
            ):
                return True
    return False


# --- worked examples from the box ------------------------------------------


#: Costs this board can and cannot pay. Two Forests, an Island, a Mountain and
#: Llanowar Elves -- so plenty of green, one blue, one red.
CASTABLE = ["{G}", "{1}{G}", "{2}{G}{G}", "{1}{U}", ""]
UNCASTABLE = ["{U}{U}", "{4}{G}{G}", "{R}{R}"]


@pytest.mark.parametrize("cost", CASTABLE)
def test_costs_this_board_can_pay(cost: str) -> None:
    assert can_pay(parse(cost), BOARD)


@pytest.mark.parametrize("cost", UNCASTABLE)
def test_costs_this_board_cannot_pay(cost: str) -> None:
    assert not can_pay(parse(cost), BOARD)


def test_it_keeps_the_other_colour_up() -> None:
    """The advice a beginner never gets: pay with Forests, keep the Island."""
    best = payments(parse("{1}{G}"), BOARD)[0]
    assert "island" in best.spare
    assert best.count == 2


def test_the_best_payment_taps_the_fewest_sources() -> None:
    for payment in payments(parse("{2}{G}"), BOARD):
        assert payment.count == 3, "a three-mana cost always taps three"


def test_payments_are_distinct() -> None:
    ways = payments(parse("{1}{G}"), BOARD)
    assert len({p.tapped for p in ways}) == len(ways)


def test_a_free_cost_needs_nothing() -> None:
    assert payments(ManaCost(), BOARD)[0].tapped == ()


def test_colorless_costs_are_refused_rather_than_treated_as_generic() -> None:
    """No source in the box makes {C}; pretending otherwise would mislead."""
    assert payments(parse("{C}"), BOARD) == ()


def test_an_empty_board_pays_only_a_free_cost() -> None:
    assert can_pay(ManaCost(), [])
    assert not can_pay(parse("{G}"), [])


def test_x_is_solved_as_zero() -> None:
    """The caller folds a chosen X into the generic part and asks again."""
    assert can_pay(parse("{X}{G}"), [land("forest", "G")])


# --- properties ------------------------------------------------------------

costs = st.builds(
    ManaCost,
    generic=st.integers(0, 3),
    symbols=st.lists(
        st.sets(st.sampled_from(COLORS), min_size=1, max_size=2).map(frozenset),
        max_size=3,
    ).map(tuple),
)
boards = st.lists(
    st.sets(st.sampled_from(COLORS), min_size=0, max_size=2).map(frozenset),
    max_size=5,
).map(lambda colors: [ManaSource(InstanceId(f"s{i}"), c) for i, c in enumerate(colors)])


@settings(max_examples=150, deadline=None)
@given(costs, boards)
def test_the_solver_agrees_with_the_slow_reference(
    cost: ManaCost, sources: list[ManaSource]
) -> None:
    assert can_pay(cost, sources) == _reference_can_pay(cost, sources)


@settings(max_examples=150, deadline=None)
@given(costs, boards)
def test_every_payment_actually_pays(cost: ManaCost, sources: list[ManaSource]) -> None:
    """A returned payment must be one you could really make."""
    by_id = {s.instance_id: s for s in sources}
    for payment in payments(cost, sources):
        assert len(payment.tapped) == cost.total
        assert len(set(payment.tapped)) == len(payment.tapped), "no double-tapping"
        chosen = [by_id[i] for i in payment.tapped]
        assert _reference_can_pay(cost, chosen), "the tapped sources must suffice"


@settings(max_examples=150, deadline=None)
@given(costs, boards)
def test_tapped_and_spare_partition_the_board(cost: ManaCost, sources: list[ManaSource]) -> None:
    everything = {s.instance_id for s in sources}
    for payment in payments(cost, sources):
        assert set(payment.tapped) | set(payment.spare) == everything
        assert not set(payment.tapped) & set(payment.spare)


@settings(max_examples=100, deadline=None)
@given(costs, boards)
def test_payments_are_ordered_by_how_much_they_leave_you(
    cost: ManaCost, sources: list[ManaSource]
) -> None:
    counts = [p.count for p in payments(cost, sources)]
    assert counts == sorted(counts)
