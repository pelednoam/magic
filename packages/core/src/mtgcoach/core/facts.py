"""What the engine needs to know about a card.

``core`` holds no card data -- that is ``carddata``'s job, and the separation is
what keeps a reprint from becoming a different card. But legality and combat
cannot be answered without *some* facts, so this is the narrow view they take:
built by the caller from a real card, and containing only what a rules question
actually needs.

Power and toughness are integers here, not the strings Scryfall stores. A card
whose power is ``*`` has no fixed value, so it arrives as None and every
consumer has to say what it does about that -- which is better than a silent
zero that makes a 4/4 Consuming Aberration look harmless.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.ids import OracleId
    from mtgcoach.core.manacost import ManaCost


@dataclass(frozen=True, slots=True)
class CardFacts:
    """The rules-relevant properties of one card."""

    oracle_id: OracleId
    name: str
    cost: ManaCost
    is_land: bool = False
    is_creature: bool = False
    is_instant_speed: bool = False
    power: int | None = None
    toughness: int | None = None
    keywords: frozenset[str] = field(default_factory=frozenset[str])

    def has(self, keyword: str) -> bool:
        """Whether the card has a keyword, compared without regard to case."""
        wanted = keyword.casefold()
        return any(k.casefold() == wanted for k in self.keywords)
