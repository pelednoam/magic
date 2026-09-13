"""Card-shape classification."""

from __future__ import annotations

import pytest
from hypothesis import given
from hypothesis import strategies as st

from mtgcoach.vision.geometry import (
    CARD_ASPECT,
    DEFAULT_TOLERANCE,
    Orientation,
    classify_quad,
)

heights = st.floats(min_value=1.0, max_value=10_000.0, allow_nan=False)


def test_card_aspect_is_the_physical_ratio() -> None:
    assert pytest.approx(63.0 / 88.0) == CARD_ASPECT
    assert pytest.approx(0.7159, abs=1e-4) == CARD_ASPECT


@given(heights)
def test_exact_card_proportions_classify_upright(height: float) -> None:
    assert classify_quad(height * CARD_ASPECT, height) is Orientation.UPRIGHT


@given(heights)
def test_a_quarter_turn_classifies_tapped(height: float) -> None:
    assert classify_quad(height, height * CARD_ASPECT) is Orientation.TAPPED


@given(heights)
def test_a_square_is_never_a_card(side: float) -> None:
    assert classify_quad(side, side) is None


def test_within_tolerance_still_classifies() -> None:
    height = 100.0
    nudged = height * CARD_ASPECT * (1 + DEFAULT_TOLERANCE * 0.9)
    assert classify_quad(nudged, height) is Orientation.UPRIGHT


def test_outside_tolerance_is_rejected() -> None:
    height = 100.0
    stretched = height * CARD_ASPECT * (1 + DEFAULT_TOLERANCE * 3)
    assert classify_quad(stretched, height) is None


def test_zero_tolerance_accepts_only_the_exact_ratio() -> None:
    assert classify_quad(CARD_ASPECT, 1.0, tolerance=0.0) is Orientation.UPRIGHT


@pytest.mark.parametrize(("width", "height"), [(0.0, 10.0), (10.0, 0.0), (-1.0, 10.0)])
def test_non_positive_dimensions_are_an_error(width: float, height: float) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        classify_quad(width, height)


def test_negative_tolerance_is_an_error() -> None:
    with pytest.raises(ValueError, match="tolerance must be non-negative"):
        classify_quad(63.0, 88.0, tolerance=-0.1)
