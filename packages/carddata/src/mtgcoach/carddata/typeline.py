"""Parsing a type line into supertypes, types and subtypes.

Magic writes a type line as ``Legendary Creature — Angel``: supertypes and card
types before an em dash, subtypes after it. Almost every legality question in
the engine is really a question about this string, so it is parsed once here
rather than string-matched at each call site.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: U+2014. Scryfall always uses an em dash, never a hyphen; splitting on "-"
#: would cut "Elf Warlock" out of "Legendary Creature — Elf Warlock" incorrectly
#: only for hyphenated subtypes, which is exactly the kind of bug that hides.
TYPE_SEPARATOR: Final = "—"

#: CR 205.4a. Everything else before the dash is a card type.
SUPERTYPES: Final[frozenset[str]] = frozenset(
    {"Basic", "Legendary", "Ongoing", "Snow", "World", "Elite", "Host"}
)


@dataclass(frozen=True, slots=True)
class TypeLine:
    """One face's parsed type line."""

    supertypes: frozenset[str]
    types: frozenset[str]
    subtypes: frozenset[str]

    @property
    def is_land(self) -> bool:
        """Whether this face is a land."""
        return "Land" in self.types

    @property
    def is_creature(self) -> bool:
        """Whether this face is a creature."""
        return "Creature" in self.types

    @property
    def is_permanent(self) -> bool:
        """Whether this face stays on the battlefield (CR 110.1)."""
        return bool(self.types & PERMANENT_TYPES)

    @property
    def is_instant_speed(self) -> bool:
        """Whether this face can be cast at instant speed on its own."""
        return "Instant" in self.types


#: CR 110.1. Everything else is cast and then leaves the stack.
PERMANENT_TYPES: Final[frozenset[str]] = frozenset(
    {"Artifact", "Battle", "Creature", "Enchantment", "Land", "Planeswalker"}
)


def parse_type_line(text: str) -> TypeLine:
    """Split a type line into its three parts.

    An empty or dash-less line yields empty subtypes rather than an error: a
    token like ``Instant`` is a complete, legal type line.
    """
    before, _, after = text.partition(TYPE_SEPARATOR)
    words = before.split()
    supertypes = frozenset(w for w in words if w in SUPERTYPES)
    return TypeLine(
        supertypes=supertypes,
        types=frozenset(words) - supertypes,
        subtypes=frozenset(after.split()),
    )
