"""What the exact search will and will not take on.

The numbers here were measured, not derived: two earlier versions of this
bound counted a dimension and told a story about it, and both admitted boards
that take minutes.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING

import pytest

from helpers import creature
from mtgcoach.core.combat.budget import (
    MAX_ATTACKERS,
    MAX_BLOCKERS,
    MAX_RESOLUTIONS,
    TooManyCombinationsError,
    arrangements,
    check_defence_size,
    check_plan_size,
    resolutions_for,
)
from mtgcoach.core.combat.search import best_defence, plans

if TYPE_CHECKING:
    from mtgcoach.core.combat.model import Creature

#: The budget is a time budget, and this is the claim it rests on: no board it
#: admits may take longer than this. Deliberately loose -- it is here to catch a
#: change that makes resolving a combat an order of magnitude slower, not to
#: pin this machine to a number.
SLOWEST_ALLOWED_SECONDS = 30.0

#: A board small enough to time in a unit test, used to measure the per-combat
#: cost that the budget is calibrated against.
CALIBRATION = (4, 4)

#: How many times to measure, keeping the fastest. A wall clock in a unit suite
#: measures the machine's load as much as the code's cost, and the whole suite
#: under coverage is exactly when it is most loaded -- this test failed once in
#: a full run and passed every time on its own, which is a false alarm about
#: the one thing it exists to raise a true alarm about. The fastest of several
#: runs is the machine's capability; the slowest is the neighbours.
SAMPLES = 5


def _some(count: int, prefix: str) -> list[Creature]:
    return [creature(f"{prefix}{i}", 2, 2) for i in range(count)]


def test_the_blockers_are_the_exponent() -> None:
    """Which is why capping only the attackers guarded nothing."""
    assert resolutions_for(2, 8) > resolutions_for(8, 2)


def test_the_count_is_for_every_attack_subset_not_one() -> None:
    """`plans` runs a whole blocking search per subset, and 2^A of them."""
    assert resolutions_for(8, 6) > (8 + 1) ** 6


def test_an_empty_board_is_one_resolution() -> None:
    assert resolutions_for(0, 0) == 1


def test_one_attacker_too_many_is_refused() -> None:
    with pytest.raises(TooManyCombinationsError, match="attackers"):
        check_plan_size(_some(MAX_ATTACKERS + 1, "a"), [])


def test_one_blocker_too_many_is_refused() -> None:
    with pytest.raises(TooManyCombinationsError, match="blockers"):
        check_plan_size([], _some(MAX_BLOCKERS + 1, "b"))


def test_both_dimensions_at_their_caps_is_refused() -> None:
    """The flaw in both previous limit tests: neither used both at once.

    Eight attackers against six blockers passes every per-dimension guard and
    takes five minutes.
    """
    with pytest.raises(TooManyCombinationsError, match="combats to resolve"):
        check_plan_size(_some(MAX_ATTACKERS, "a"), _some(MAX_BLOCKERS, "b"))


def test_plans_refuses_the_same_board() -> None:
    with pytest.raises(TooManyCombinationsError):
        plans(_some(MAX_ATTACKERS, "a"), _some(MAX_BLOCKERS, "b"), 20)


def test_a_single_defence_is_cheaper_than_the_whole_enumeration() -> None:
    """`best_defence` searches one attack, so it takes boards `plans` will not.

    The two counts are asserted rather than quoted: the numbers in this
    docstring went stale the moment the enumeration changed shape, and a stale
    number in a test is worse than none.
    """
    attackers, blockers = _some(8, "a"), _some(4, "b")
    assert arrangements(8, 4) < MAX_RESOLUTIONS < resolutions_for(8, 4)
    check_defence_size(attackers, blockers)
    with pytest.raises(TooManyCombinationsError, match="combats to resolve"):
        check_plan_size(attackers, blockers)


def test_best_defence_refuses_an_oversized_board_too() -> None:
    with pytest.raises(TooManyCombinationsError, match="blockers"):
        best_defence([creature("Bear", 2, 2)], _some(MAX_BLOCKERS + 1, "b"), 20)


@pytest.mark.parametrize(("attackers", "blockers"), [(8, 3), (6, 4), (4, 4), (5, 4)])
def test_a_real_board_is_allowed(attackers: int, blockers: int) -> None:
    """The shapes a Beginner Box game actually produces."""
    check_plan_size(_some(attackers, "a"), _some(blockers, "b"))


def test_no_board_the_budget_admits_can_hang() -> None:
    """Measured on a small board, extrapolated to the largest one allowed.

    Timing the worst allowed board directly would put a three-second case in a
    unit suite; timing a small one and multiplying makes the same claim, and
    fails just as loudly if resolving a combat gets much more expensive.

    The *fastest* of several runs, because a single wall-clock reading in a
    unit suite measures the machine's load as much as the code's cost. This
    failed once in a full run under coverage and passed every time on its own,
    which is the failure mode that teaches people to ignore a red test.
    """
    attackers, blockers = CALIBRATION
    board = (_some(attackers, "a"), _some(blockers, "b"))
    fastest = min(_timed(board) for _ in range(SAMPLES))
    per_combat = fastest / resolutions_for(attackers, blockers)
    assert per_combat * MAX_RESOLUTIONS < SLOWEST_ALLOWED_SECONDS


def _timed(board: tuple[list[Creature], list[Creature]]) -> float:
    """How long one search of this board takes."""
    attackers, blockers = board
    start = time.perf_counter()
    plans(attackers, blockers, 20)
    return time.perf_counter() - start


def test_the_refusal_is_a_value_error() -> None:
    """Callers that catch the `*`-power refusal catch this one too."""
    assert issubclass(TooManyCombinationsError, ValueError)
