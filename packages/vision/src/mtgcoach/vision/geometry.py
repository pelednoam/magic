"""Card geometry.

A Magic card is 63 x 88 mm regardless of set, so the aspect ratio is the one
reliable filter for telling a card-shaped quadrilateral from the rest of a
photo -- and a tapped card is the same rectangle rotated a quarter turn, which
is how orientation comes out of detection for free.
"""

from __future__ import annotations

import math
from enum import StrEnum
from typing import Final

CARD_WIDTH_MM: Final = 63.0
CARD_HEIGHT_MM: Final = 88.0

#: Width divided by height for an untapped card: approximately 0.716.
CARD_ASPECT: Final = CARD_WIDTH_MM / CARD_HEIGHT_MM

#: Default relative tolerance on the aspect ratio. Generous enough to absorb
#: the perspective distortion of a phone held over a table, tight enough that
#: a square or a playmat edge is rejected.
DEFAULT_TOLERANCE: Final = 0.08


class Orientation(StrEnum):
    """How a detected card sits relative to the player."""

    UPRIGHT = "upright"
    TAPPED = "tapped"


def _within(ratio: float, target: float, tolerance: float) -> bool:
    return abs(ratio - target) <= target * tolerance


def classify_quad(
    width_px: float,
    height_px: float,
    tolerance: float = DEFAULT_TOLERANCE,
) -> Orientation | None:
    """Classify a detected quadrilateral by its aspect ratio.

    Args:
        width_px: Width of the quad's bounding box, in pixels.
        height_px: Height of the quad's bounding box, in pixels.
        tolerance: Relative tolerance on the aspect ratio.

    Returns:
        ``UPRIGHT`` if the quad is card-shaped, ``TAPPED`` if it is card-shaped
        rotated a quarter turn, and ``None`` if it is not a card at all.

    Raises:
        ValueError: If either dimension is not finite and strictly positive, or
            if ``tolerance`` is not finite and non-negative.
    """
    # Every comparison against NaN is False, so `width_px <= 0` waves NaN
    # through and the function returns None -- "not a card" -- instead of
    # reporting that the detector handed us garbage. Contour geometry divides,
    # so 0/0 and inf/inf reach here as NaN in practice.
    if not (math.isfinite(width_px) and math.isfinite(height_px)):
        msg = f"quad dimensions must be finite, got {width_px}x{height_px}"
        raise ValueError(msg)
    if width_px <= 0 or height_px <= 0:
        msg = f"quad dimensions must be positive, got {width_px}x{height_px}"
        raise ValueError(msg)
    if not math.isfinite(tolerance):
        msg = f"tolerance must be finite, got {tolerance}"
        raise ValueError(msg)
    if tolerance < 0:
        msg = f"tolerance must be non-negative, got {tolerance}"
        raise ValueError(msg)

    ratio = width_px / height_px
    if _within(ratio, CARD_ASPECT, tolerance):
        return Orientation.UPRIGHT
    if _within(ratio, 1.0 / CARD_ASPECT, tolerance):
        return Orientation.TAPPED
    return None
