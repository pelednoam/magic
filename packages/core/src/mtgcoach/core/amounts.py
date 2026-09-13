"""How much: a fixed number, or one the board decides.

``Bite Down`` deals damage "equal to its power", and ``Felling Blow`` does the
same after adding a counter. A plain integer cannot say that, and storing the
phrase as text would put it back beyond the engine's reach -- so an amount is
either a number or a named quantity the engine knows how to look up.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Quantity(StrEnum):
    """A number read off the game state when the effect resolves."""

    #: The power of whatever is dealing the damage -- the card itself, or the
    #: permanent named by ``DealDamage.source`` when there is one.
    SOURCE_POWER = "source_power"
    SOURCE_TOUGHNESS = "source_toughness"
    TARGET_POWER = "target_power"
    X = "x"


@dataclass(frozen=True, slots=True)
class Dynamic:
    """An amount determined when the effect resolves."""

    quantity: Quantity


#: Either a literal number or something looked up at resolution.
type Amount = int | Dynamic
