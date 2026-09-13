"""How large a board the solver will answer for, and how it refuses.

The old search enumerated ordered assignments of sources to pips, which is
factorial; these are the cases that would have hung it.
"""

from __future__ import annotations

import pytest

from mtgcoach.core.ids import InstanceId
from mtgcoach.core.manacost import ManaSource, parse
from mtgcoach.core.manasolver import (
    MAX_PAYMENTS,
    TooManyPaymentsError,
    can_pay,
    options,
    payments,
)

COLORS = "WUBRG"


def land(name: str, colors: str) -> ManaSource:
    return ManaSource(InstanceId(name), frozenset(colors))


def test_matching_beats_the_greedy_choice() -> None:
    """A dual land taken for the wrong pip must be given back.

    {W}{U} from a Plains and a W/U dual: assign the dual to {W} first and {U}
    has nothing left, though the payment plainly exists.
    """
    plains = land("plains", "W")
    dual = land("dual", "WU")
    assert can_pay(parse("{W}{U}"), [plains, dual])


def test_a_long_displacement_chain_still_matches() -> None:
    """Three symbols where every early choice has to be pushed along."""
    sources = [land("wu", "WU"), land("ub", "UB"), land("b", "B")]
    assert can_pay(parse("{W}{U}{B}"), sources)


def test_can_pay_does_not_enumerate_the_whole_board() -> None:
    """It must stop at the first payment, not build the ranked list."""
    huge = [land(f"any-{i}", COLORS) for i in range(30)]
    assert can_pay(parse("{W}{U}{B}{R}{G}"), huge)
    with pytest.raises(TooManyPaymentsError):
        payments(parse("{W}{U}{B}{R}{G}"), huge)


def test_a_board_too_large_to_rank_is_refused_not_truncated() -> None:
    huge = [land(f"any-{i}", COLORS) for i in range(30)]
    with pytest.raises(TooManyPaymentsError, match="cannot rank them exactly"):
        payments(parse("{4}{W}"), huge)


def test_the_limit_is_not_hit_by_a_real_board() -> None:
    """Twelve sources and a five-pip cost is what a late game actually looks like."""
    board = [land(f"any-{i}", COLORS) for i in range(12)]
    assert len(payments(parse("{2}{W}{U}{B}"), board)) < MAX_PAYMENTS


def test_options_yields_each_set_of_sources_once() -> None:
    """A source can be reached as a coloured pip or as generic; it is one payment."""
    board = [land("wu-1", "WU"), land("wu-2", "WU"), land("wu-3", "WU")]
    tapped = [p.tapped for p in options(parse("{1}{W}"), board)]
    assert len(tapped) == len(set(tapped)) == 3


def test_options_is_empty_for_a_colourless_pip() -> None:
    assert list(options(parse("{C}"), [land("forest", "G")])) == []
