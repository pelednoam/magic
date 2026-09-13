"""Colour from mana cost (CR 202.2), including costs the solver refuses."""

from __future__ import annotations

import pytest

from mtgcoach.carddata.facecolors import colors_in


@pytest.mark.parametrize(
    ("cost", "expected"),
    [
        ("{1}{B}", {"B"}),
        ("{2}{R}{R}{W}{W}", {"R", "W"}),
        ("{U}", {"U"}),
        ("{3}", set[str]()),
        ("", set[str]()),
        ("{X}{U}", {"U"}),
        ("{C}", set[str]()),
        ("{S}", set[str]()),
        ("{W/U}{W/U}", {"W", "U"}),
        ("{2/W}", {"W"}),
        ("{G/P}", {"G"}),
        ("{W}{U}{B}{R}{G}", {"W", "U", "B", "R", "G"}),
    ],
)
def test_colors_in(cost: str, expected: set[str]) -> None:
    assert colors_in(cost) == expected


def test_letters_outside_braces_are_not_colours() -> None:
    """A stray letter in a malformed cost must not invent a colour."""
    assert colors_in("BRG") == frozenset()


@pytest.mark.parametrize(
    ("cost", "expected"),
    [("{2/W}", {"W"}), ("{G/P}", {"G"}), ("{W/U/B}", {"W", "U", "B"})],
)
def test_costs_the_solver_refuses_still_yield_colours(cost: str, expected: set[str]) -> None:
    """Ingestion must not fail on a cost the solver cannot model.

    A set full of hybrid symbols should still import; those cards are simply
    unplayable until the solver grows.
    """
    assert colors_in(cost) == expected
