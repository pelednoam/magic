"""Preconstructed decklists, and whether we actually believe them.

A decklist that is quietly incomplete is worse than no decklist. The coach
reasons about what is left in an opponent's library -- "they have two burn
spells still in there" -- and that reasoning is only sound if the list is whole.
A list short by two cards produces confident, specific, wrong advice.

So completeness is **computed, never declared**. ``Decklist`` has no field
saying whether it is complete, because a field like that can be wrong in the
data file and nobody would notice. ``verify`` asks two independent questions
instead:

1. Do the quantities total exactly the deck size?
2. Does every name resolve to a real card in the set?

Both matter, and the second caught a real error. An earlier transcription of the
Goblins deck contained "Volley", "Veteran Goblin" and "Firebomb"; the actual
cards are ``Volley Veteran`` and ``Goblin Firebomb``. The totals check alone
would not have found it -- it made the deck 21 cards, which merely looks like a
miscount -- but no card named "Firebomb" exists in Foundations, and that is not
arguable.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Final

from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    as_array,
    as_object,
    optional_str,
    require_str,
)
from mtgcoach.carddata.paths import decks_dir

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.core.ids import SetCode

#: Cards in one Jumpstart half-deck. Two shuffled together make a 40-card deck.
JUMPSTART_DECK_SIZE: Final = 20


class Completeness(StrEnum):
    """Whether a decklist can be reasoned about."""

    VERIFIED = "verified"
    PARTIAL = "partial"


@dataclass(frozen=True, slots=True)
class DeckEntry:
    """One line of a decklist."""

    name: str
    quantity: int

    def __post_init__(self) -> None:
        """Reject a quantity that is not a number of physical cards.

        The loader checks this too, but a decklist can also be built directly --
        by a deck importer, or a scan -- and a zero-quantity entry would make
        ``total`` disagree with the cards actually present.

        Raises:
            ValueError: If the quantity is not a positive integer.
        """
        if self.quantity < 1:
            msg = f"{self.name}: quantity must be positive, got {self.quantity}"
            raise ValueError(msg)


@dataclass(frozen=True, slots=True)
class Decklist:
    """A preconstructed deck, as transcribed from its sources."""

    key: str
    name: str
    color: str
    tutorial: bool
    sources: tuple[str, ...]
    entries: tuple[DeckEntry, ...]

    @property
    def total(self) -> int:
        """How many physical cards this list accounts for."""
        return sum(entry.quantity for entry in self.entries)

    @property
    def names(self) -> tuple[str, ...]:
        """Every distinct card name in the list."""
        return tuple(entry.name for entry in self.entries)


@dataclass(frozen=True, slots=True)
class DeckVerdict:
    """The result of checking a decklist. Never stored, always recomputed."""

    completeness: Completeness
    total: int
    expected: int
    unknown_names: tuple[str, ...]

    @property
    def is_verified(self) -> bool:
        """Whether the coach may reason about this deck's contents."""
        return self.completeness is Completeness.VERIFIED

    @property
    def reasons(self) -> tuple[str, ...]:
        """Plain-language explanations, empty when verified."""
        problems: list[str] = []
        if self.total != self.expected:
            problems.append(f"{self.total} cards listed, expected {self.expected}")
        if self.unknown_names:
            joined = ", ".join(self.unknown_names)
            problems.append(f"not cards in this set: {joined}")
        return tuple(problems)


def verify(
    deck: Decklist,
    known_names: frozenset[str],
    expected: int = JUMPSTART_DECK_SIZE,
) -> DeckVerdict:
    """Check a decklist against its expected size and the cards that exist."""
    unknown = tuple(sorted({n for n in deck.names if n not in known_names}))
    complete = deck.total == expected and not unknown
    return DeckVerdict(
        completeness=Completeness.VERIFIED if complete else Completeness.PARTIAL,
        total=deck.total,
        expected=expected,
        unknown_names=unknown,
    )


def load_decklist(path: Path) -> Decklist:
    """Read one decklist file.

    Raises:
        MalformedJsonError: If the document is not an object, or a required
            field is missing or has the wrong type.
    """
    parsed: object = json.loads(path.read_text(encoding="utf-8"))
    doc = as_object(parsed)
    if doc is None:
        msg = f"{path.name}: not a JSON object"
        raise MalformedJsonError(msg)

    key = require_str(doc, "key", path.name)
    cards = as_array(doc.get("cards")) or []
    entries: list[DeckEntry] = []
    for raw in cards:
        entry = as_object(raw)
        if entry is None:
            msg = f"{key}: a card entry is not an object"
            raise MalformedJsonError(msg)
        entries.append(
            DeckEntry(
                name=require_str(entry, "name", key),
                quantity=_quantity(entry.get("quantity"), key),
            )
        )
    return Decklist(
        key=key,
        name=optional_str(doc, "name", key),
        color=optional_str(doc, "color"),
        tutorial=doc.get("tutorial") is True,
        sources=tuple(s for s in as_array(doc.get("sources")) or [] if isinstance(s, str)),
        entries=tuple(entries),
    )


def _quantity(value: object, context: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        msg = f"{context}: quantity must be a positive integer, got {value!r}"
        raise MalformedJsonError(msg)
    return value


def load_set_decks(data_root: Path, set_code: SetCode) -> tuple[Decklist, ...]:
    """Read every decklist shipped for one set, ordered by file name."""
    directory = decks_dir(data_root, set_code)
    return tuple(load_decklist(p) for p in sorted(directory.glob("*.json")))
