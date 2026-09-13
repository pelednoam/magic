"""Static card data: what a card is, independent of any game.

Modelled face-first because the real data requires it. A transform card carries
no top-level ``mana_cost`` or ``oracle_text`` at all -- both live on the faces --
and an adventure card's top-level cost is the useless combined string
``{3} // {1}{B}``. Treating a card as one face works until the first
double-faced card arrives and then has to be unpicked everywhere, so every card
here has a tuple of faces, of length one in the ordinary case.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.carddata.typeline import TypeLine, parse_type_line

if TYPE_CHECKING:
    from mtgcoach.core.ids import OracleId


@dataclass(frozen=True, slots=True)
class CardFace:
    """One printed face of a card."""

    name: str
    mana_cost: str
    type_line: str
    oracle_text: str
    power: str | None
    toughness: str | None
    colors: frozenset[str]

    @property
    def types(self) -> TypeLine:
        """The parsed type line.

        Recomputed per call rather than cached: ``slots=True`` leaves no
        ``__dict__`` for ``cached_property`` to write into, and splitting a
        short string is cheaper than the memory a cache would cost across a
        few hundred cards.
        """
        return parse_type_line(self.type_line)


@dataclass(frozen=True, slots=True)
class Card:
    """An oracle card: rules behaviour, independent of printing.

    ``cmc`` is a float because Scryfall's is. Halves exist only in Un-sets, but
    silently truncating data we were handed is how a store stops matching its
    source.
    """

    oracle_id: OracleId
    name: str
    cmc: float
    layout: str
    keywords: frozenset[str]
    color_identity: frozenset[str]
    produced_mana: frozenset[str]
    faces: tuple[CardFace, ...]

    @property
    def front(self) -> CardFace:
        """The face a card is cast from, and the one a scan sees."""
        return self.faces[0]

    @property
    def is_multifaced(self) -> bool:
        """Whether this card has more than one printed face."""
        return len(self.faces) > 1
