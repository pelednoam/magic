"""What the exact search will and will not take on."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from helpers import creature

if TYPE_CHECKING:
    from mtgcoach.core.combat.model import Creature
from mtgcoach.core.combat.budget import (
    MAX_ATTACKERS,
    MAX_BLOCKERS,
    MAX_COMBINATIONS,
    TooManyCombinationsError,
    check_size,
    combinations_for,
)


def _some(count: int, prefix: str) -> list[Creature]:
    return [creature(f"{prefix}{i}", 1, 1) for i in range(count)]


def test_the_blockers_are_the_exponent() -> None:
    """Which is why capping only the attackers guarded nothing."""
    assert combinations_for(8, 8) > combinations_for(8, 2)
    assert combinations_for(2, 8) > combinations_for(8, 2)


def test_an_empty_board_is_one_assignment() -> None:
    assert combinations_for(0, 0) == 1


def test_a_board_at_both_limits_is_allowed() -> None:
    check_size(_some(MAX_ATTACKERS, "a"), _some(MAX_BLOCKERS, "b"))


def test_one_attacker_too_many_is_refused() -> None:
    with pytest.raises(TooManyCombinationsError, match="attackers"):
        check_size(_some(MAX_ATTACKERS + 1, "a"), [])


def test_one_blocker_too_many_is_refused() -> None:
    with pytest.raises(TooManyCombinationsError, match="blockers"):
        check_size([], _some(MAX_BLOCKERS + 1, "b"))


def test_the_work_itself_is_bounded_not_only_the_dimensions() -> None:
    """The product is the thing that hangs, so it is checked on its own."""
    assert combinations_for(MAX_ATTACKERS, MAX_BLOCKERS) <= MAX_COMBINATIONS


def test_the_product_guard_fires_when_the_dimensions_pass() -> None:
    with (
        patch("mtgcoach.core.combat.budget.MAX_COMBINATIONS", 1),
        pytest.raises(TooManyCombinationsError, match="block assignments"),
    ):
        check_size(_some(2, "a"), _some(2, "b"))


def test_the_refusal_is_a_value_error() -> None:
    """Callers that catch the `*`-power refusal catch this one too."""
    assert issubclass(TooManyCombinationsError, ValueError)
