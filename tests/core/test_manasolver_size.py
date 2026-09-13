"""How large a board the solver will answer for, and how it refuses.

The first search enumerated ordered assignments of sources to pips, which is
factorial; these are the cases that would have hung it, plus the two caller
mistakes that used to produce a confident wrong answer instead of an error.
"""

from __future__ import annotations

import math
import time

import pytest

from mtgcoach.core.ids import InstanceId
from mtgcoach.core.manacost import ManaSource, parse
from mtgcoach.core.manasolver import (
    MAX_SOURCES,
    DuplicateSourceError,
    TooManySourcesError,
    can_pay,
    options,
    payments,
)

COLORS = "WUBRG"

#: A search this size has to finish quickly whether or not a payment exists.
SLOWEST_ALLOWED_SECONDS = 2.0


def land(name: str, colors: str) -> ManaSource:
    return ManaSource(InstanceId(name), frozenset(colors))


def _board(count: int, colors: str = COLORS) -> list[ManaSource]:
    return [land(f"any-{i}", colors) for i in range(count)]


def test_the_same_permanent_cannot_be_tapped_twice() -> None:
    """One Forest passed twice used to pay {G}{G}, and say which: ('f', 'f')."""
    forest = land("forest", "G")
    with pytest.raises(DuplicateSourceError, match="one permanent"):
        payments(parse("{G}{G}"), [forest, forest])


def test_can_pay_refuses_a_duplicate_too() -> None:
    forest = land("forest", "G")
    with pytest.raises(DuplicateSourceError):
        can_pay(parse("{G}"), [forest, forest])


def test_too_many_sources_is_refused_rather_than_searched() -> None:
    with pytest.raises(TooManySourcesError, match="untapped sources"):
        payments(parse("{W}"), _board(MAX_SOURCES + 1))


def test_the_source_limit_itself_is_allowed() -> None:
    assert can_pay(parse("{W}"), _board(MAX_SOURCES))


def test_an_unpayable_cost_is_answered_as_fast_as_a_payable_one() -> None:
    """The expensive case is the *failure*, which is what legality asks about.

    `can_pay` stops at the first payment, so a castable spell is cheap; an
    uncastable one scans the whole space and finds nothing, and that is the
    question asked once per card in hand.
    """
    board = _board(MAX_SOURCES, "G")
    start = time.perf_counter()
    assert not can_pay(parse("{W}{U}{B}{R}{G}"), board)
    assert time.perf_counter() - start < SLOWEST_ALLOWED_SECONDS


def test_the_source_cap_bounds_the_payment_count_too() -> None:
    """Which is why there is no second limit on payments: it cannot be reached."""
    assert len(payments(parse("{6}{W}{U}"), _board(MAX_SOURCES))) == math.comb(MAX_SOURCES, 8)


def test_a_real_board_produces_a_readable_number_of_payments() -> None:
    """Twelve sources and a four-mana cost is what a late game looks like."""
    assert len(payments(parse("{2}{W}{U}"), _board(12))) == math.comb(12, 4)


def test_options_yields_each_set_of_sources_once() -> None:
    """A source can be reached as a coloured pip or as generic; it is one payment."""
    board = [land("wu-1", "WU"), land("wu-2", "WU"), land("wu-3", "WU")]
    tapped = [p.tapped for p in options(parse("{1}{W}"), board)]
    assert len(tapped) == len(set(tapped)) == 3


def test_a_colourless_pip_is_paid_by_a_colourless_source() -> None:
    """ManaSource documents an empty colour set as colourless production."""
    wastes = ManaSource(InstanceId("wastes"), frozenset())
    assert can_pay(parse("{C}"), [wastes])


def test_a_colourless_pip_is_not_paid_by_a_coloured_source() -> None:
    assert not can_pay(parse("{C}"), [land("forest", "G")])


def test_a_colourless_source_still_pays_generic() -> None:
    wastes = ManaSource(InstanceId("wastes"), frozenset())
    assert can_pay(parse("{1}"), [wastes])
