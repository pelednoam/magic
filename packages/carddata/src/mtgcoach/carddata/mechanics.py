"""Which mechanics the engine understands, and what a new set would cost.

The honest answer to "can the coach handle this set?" is per mechanic, not per
set. ``audit`` turns that into a number you can look at before spending an
evening on a set: how many cards use something the engine cannot model yet.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

    from mtgcoach.carddata.cards import Card
    from mtgcoach.core.ids import SetCode

#: Keywords the engine actually models, each with a tested implementation.
#:
#: Empty until M4, because until then there was no combat and no legality to
#: model them in, and a registry seeded with optimistic guesses would have made
#: this report decoration. Every entry below is here because a specific rule
#: reads it and a test pins the behaviour:
#:
#: - Flying and Reach decide who may block (CR 702.9b).
#: - First strike and Double strike decide which damage step a creature deals in.
#: - Deathtouch makes any nonzero damage lethal (CR 702.2b).
#: - Trample spills the excess through to the defender.
#: - Lifelink turns damage dealt into life gained.
#: - Menace requires two blockers or none (CR 702.111b).
#: - Indestructible survives lethal damage.
#: - Defender cannot attack; Haste attacks the turn it arrives.
#:
#: Vigilance is deliberately absent. It governs whether attacking taps the
#: creature, and nothing taps attackers yet, so claiming it would be the kind of
#: overstatement this registry exists to prevent.
SUPPORTED_KEYWORDS: Final[frozenset[str]] = frozenset(
    {
        "Flying",
        "Reach",
        "First strike",
        "Double strike",
        "Deathtouch",
        "Trample",
        "Lifelink",
        "Menace",
        "Indestructible",
        "Defender",
        "Haste",
    }
)


@dataclass(frozen=True, slots=True)
class SetAudit:
    """What it would take to coach with a given set."""

    set_code: SetCode
    card_count: int
    keyword_counts: Mapping[str, int]
    unsupported: tuple[str, ...]
    affected_cards: int

    @property
    def fully_supported(self) -> bool:
        """Whether every mechanic in the set is already modelled."""
        return not self.unsupported

    @property
    def affected_fraction(self) -> float:
        """Share of cards using at least one unmodelled mechanic."""
        if self.card_count == 0:
            return 0.0
        return self.affected_cards / self.card_count


def audit(
    set_code: SetCode,
    cards: Iterable[Card],
    supported: frozenset[str] = SUPPORTED_KEYWORDS,
) -> SetAudit:
    """Report the mechanics in ``cards`` and which of them are unmodelled.

    ``supported`` is a parameter rather than a module lookup so that the report
    can be run against a hypothetical registry -- "what would this set cost if I
    implemented trample first?" -- without editing the registry to find out.
    """
    counts: collections.Counter[str] = collections.Counter()
    total = 0
    affected = 0
    for card in cards:
        total += 1
        counts.update(card.keywords)
        if card.keywords - supported:
            affected += 1
    return SetAudit(
        set_code=set_code,
        card_count=total,
        keyword_counts=dict(counts),
        unsupported=tuple(sorted(set(counts) - supported)),
        affected_cards=affected,
    )
