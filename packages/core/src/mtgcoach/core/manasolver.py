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
``payments`` refuses past ``MAX_PAYMENTS`` rather than returning a truncated
list that looks complete, and ``can_pay`` never reaches the limit because it
stops at the first payment it finds.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mtgcoach.core.ids import InstanceId
    from mtgcoach.core.manacost import ManaCost, ManaSource

#: How many distinct payments will be enumerated before the search gives up.
#: Chosen far above any real board -- twelve sources and a five-pip cost is a
#: few thousand -- so that reaching it means the caller passed something the
#: exact answer was never going to fit.
MAX_PAYMENTS: Final = 50_000


class TooManyPaymentsError(ValueError):
    """The board has more ways to pay than the solver will enumerate.

    Raised rather than truncated. A list of payments that silently stops short
    would rank the "best" one out of an arbitrary prefix, and the ranking is the
    part a player acts on.
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


def _can_match(symbols: Sequence[frozenset[str]], chosen: Sequence[ManaSource]) -> bool:
    """Whether every symbol can be given a distinct source from ``chosen``.

    Kuhn's algorithm: match each symbol in turn, and when its only candidates
    are taken, try to push an earlier symbol onto a different source.
    """
    partner: dict[int, int] = {}
    return all(_augment(index, symbols, chosen, partner, set()) for index in range(len(symbols)))


def _augment(
    symbol: int,
    symbols: Sequence[frozenset[str]],
    chosen: Sequence[ManaSource],
    partner: dict[int, int],
    tried: set[int],
) -> bool:
    """Find a source for ``symbol``, displacing earlier matches if it helps."""
    for index, source in enumerate(chosen):
        if index in tried or not source.can_pay(symbols[symbol]):
            continue
        tried.add(index)
        if index not in partner or _augment(partner[index], symbols, chosen, partner, tried):
            partner[index] = symbol
            return True
    return False


def _colour_sets(
    symbols: Sequence[frozenset[str]], sources: Sequence[ManaSource]
) -> Iterator[frozenset[int]]:
    """Every set of sources that can cover the coloured symbols, one each."""
    for chosen in itertools.combinations(range(len(sources)), len(symbols)):
        if _can_match(symbols, [sources[i] for i in chosen]):
            yield frozenset(chosen)


def options(cost: ManaCost, sources: Sequence[ManaSource]) -> Iterator[Payment]:
    """Every distinct payment, lazily and in no particular order.

    The lazy form exists for ``can_pay``: answering "is this castable?" by
    building the whole ranked list means a legality check on a large board costs
    what a full recommendation costs, and it is asked once per card in hand.
    """
    if cost.colorless:
        # A {C} symbol needs specifically colourless mana, which no source in
        # the box makes. Refusing beats quietly treating it as generic.
        return

    seen: set[tuple[InstanceId, ...]] = set()
    for coloured in _colour_sets(cost.symbols, sources):
        spare_indices = [i for i in range(len(sources)) if i not in coloured]
        for generic in itertools.combinations(spare_indices, cost.generic):
            used = coloured | frozenset(generic)
            key = tuple(sorted(sources[i].instance_id for i in used))
            if key in seen:
                continue
            seen.add(key)
            yield Payment(
                tapped=key,
                spare=tuple(
                    sorted(sources[i].instance_id for i in range(len(sources)) if i not in used)
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
        TooManyPaymentsError: If the board admits more than ``MAX_PAYMENTS``
            distinct payments, where an exact ranking is not worth having.
    """
    found: list[Payment] = []
    for payment in options(cost, sources):
        found.append(payment)
        if len(found) > MAX_PAYMENTS:
            msg = (
                f"more than {MAX_PAYMENTS} ways to pay {cost.total} mana from "
                f"{len(sources)} sources; cannot rank them exactly"
            )
            raise TooManyPaymentsError(msg)
    found.sort(key=lambda p: (p.count, -_flexibility(p, sources)))
    return tuple(found)


def can_pay(cost: ManaCost, sources: Sequence[ManaSource]) -> bool:
    """Whether the cost can be paid at all.

    Stops at the first payment, so this stays cheap on a board where ranking
    every payment would not be.
    """
    return any(True for _ in options(cost, sources))


def _flexibility(payment: Payment, sources: Sequence[ManaSource]) -> int:
    """How many distinct colours the untapped sources could still make."""
    by_id = {s.instance_id: s for s in sources}
    return len(frozenset[str]().union(*(by_id[i].produces for i in payment.spare), frozenset()))
