"""Can you pay for this, and which lands should you tap?

The second half of that question is the one that matters to a player. Knowing a
spell is castable is worth little; knowing to tap the Forest and *keep* the
Island up for the counterspell in hand is the advice a beginner never gets.

Structurally this is bipartite matching. Each coloured symbol must be met by a
source that makes one of its colours; generic symbols accept anything, so once
the coloured ones are matched it is only a question of how many sources remain.

The search enumerates *sets* of sources rather than assignments of sources to
symbols, and tests each set for a perfect matching. The difference is not
academic: assigning five coloured pips across twenty sources is 1.8M ordered
assignments but only 15,504 sets, and the answers are the same because a
payment is a set of lands to tap -- which one paid for which pip is not
something a player can act on.

Even so, an exact enumeration has a size, and a board can be bigger than one.
``MAX_SOURCES`` is where the refusal lives, and it is on the sources rather than
on the payments because the expensive question is the *failing* one: a cost that
cannot be paid scans the whole space and finds nothing to stop at, and that is
the question ``legality`` asks once per card in hand. With the cap in place the
payment count cannot exceed C(16, 8) either, so no second bound is needed.

``can_pay`` still stops at the first payment it finds, which makes the castable
case cheap.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mtgcoach.core.manamatch import covers

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mtgcoach.core.ids import InstanceId
    from mtgcoach.core.manacost import ManaCost, ManaSource

#: The symbol a {C} pip becomes: payable only by a source that makes no colour.
#: Represented as a set so it goes through the same matching as every other
#: symbol, with ``ManaSource.can_pay`` deciding.
_COLOURLESS: Final[frozenset[str]] = frozenset()

#: Beyond this many untapped sources the exact enumeration is not worth having.
#: A real board is a dozen; this is well past that, and the refusal is explicit
#: because the cost of the search does not depend on whether a payment exists --
#: an *unpayable* cost scans every subset and finds nothing, which is precisely
#: the question ``legality`` asks for every card in hand.
MAX_SOURCES: Final = 16


class TooManySourcesError(ValueError):
    """More untapped sources than the exact search will take on."""


class DuplicateSourceError(ValueError):
    """Two sources with one identifier -- the same permanent tapped twice.

    Payments are keyed by ``instance_id``, so a repeated one let a single Forest
    pay ``{G}{G}`` and come back as ``tapped=("forest", "forest")``. A caller
    bug, but a silent one, and the answer it produces is a spell the player
    cannot actually cast.
    """


@dataclass(frozen=True, slots=True)
class Payment:
    """One way to pay a cost: which sources to tap, and what is left untapped."""

    tapped: tuple[InstanceId, ...]
    spare: tuple[InstanceId, ...]

    @property
    def count(self) -> int:
        """How many sources this payment uses."""
        return len(self.tapped)


def options(cost: ManaCost, sources: Sequence[ManaSource]) -> Iterator[Payment]:
    """Every distinct payment, lazily and in no particular order.

    The lazy form exists for ``can_pay``: answering "is this castable?" by
    building the whole ranked list means a legality check on a large board costs
    what a full recommendation costs, and it is asked once per card in hand.
    """
    if not cost.is_payable:
        # CR 202.1a: no printed mana cost, no way to pay. The parser keeps this
        # distinct from {0}, and the solver has to honour it or a card with no
        # cost comes back castable for nothing.
        return
    _check_sources(sources)
    # A {C} pip needs specifically colourless mana, which a source with no
    # colours makes -- ManaSource documents exactly that. Refusing it outright
    # meant the coach told a player with such a source that nothing on their
    # board could make it, which is a statement about their board that the code
    # never looked at.
    symbols = (*cost.symbols, *(_COLOURLESS for _ in range(cost.colorless)))

    # One enumeration over the whole payment, not one over the coloured part
    # and another over the generic. Choosing the colours first and the generic
    # second reaches the same set of lands by many routes -- {6}{W}{U} from
    # sixteen sources visited 360,360 pairs to produce 12,870 distinct payments
    # -- and every repeat had to be recognised and discarded.
    size = len(symbols) + cost.generic
    for used in itertools.combinations(range(len(sources)), size):
        chosen = [sources[i] for i in used]
        if not covers(symbols, chosen):
            continue
        spent = frozenset(used)
        yield Payment(
            tapped=tuple(sorted(sources[i].instance_id for i in used)),
            spare=tuple(
                sorted(sources[i].instance_id for i in range(len(sources)) if i not in spent)
            ),
        )


def payments(cost: ManaCost, sources: Sequence[ManaSource]) -> tuple[Payment, ...]:
    """Every distinct way to pay ``cost`` from ``sources``, best first.

    "Best" means fewest sources tapped, then most colours left untapped -- a
    payment that leaves a Swamp and an Island up is more useful than one leaving
    two Swamps, because it keeps more of your hand live.

    An ``{X}`` cost is treated as X=0; the caller decides what to pay for X and
    asks again with it folded into the generic part.

    Raises:
        DuplicateSourceError: If two sources share an identifier.
        TooManySourcesError: If there are more untapped sources than the exact
            search will take on.
    """
    found = sorted(options(cost, sources), key=lambda p: (p.count, -_flexibility(p, sources)))
    return tuple(found)


def can_pay(cost: ManaCost, sources: Sequence[ManaSource]) -> bool:
    """Whether the cost can be paid at all.

    Stops at the first payment, so this stays cheap on a board where ranking
    every payment would not be.
    """
    return any(True for _ in options(cost, sources))


def _check_sources(sources: Sequence[ManaSource]) -> None:
    """Refuse a source list the solver cannot answer honestly for.

    Raises:
        DuplicateSourceError: If two sources share an identifier.
        TooManySourcesError: If there are more than ``MAX_SOURCES``.
    """
    ids = [s.instance_id for s in sources]
    if len(set(ids)) != len(ids):
        msg = "two sources share an identifier; one permanent cannot be tapped twice"
        raise DuplicateSourceError(msg)
    if len(sources) > MAX_SOURCES:
        msg = f"cannot search {len(sources)} untapped sources exactly (limit {MAX_SOURCES})"
        raise TooManySourcesError(msg)


def _flexibility(payment: Payment, sources: Sequence[ManaSource]) -> int:
    """How many distinct colours the untapped sources could still make."""
    by_id = {s.instance_id: s for s in sources}
    return len(frozenset[str]().union(*(by_id[i].produces for i in payment.spare), frozenset()))
