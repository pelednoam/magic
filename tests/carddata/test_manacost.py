"""Colour from mana cost (CR 105.2)."""

from __future__ import annotations

import pytest

from mtgcoach.carddata.manacost import colors_in


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
