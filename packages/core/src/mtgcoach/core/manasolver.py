"""Can you pay for this, and which lands should you tap?

The second half of that question is the one that matters to a player. Knowing a
spell is castable is worth little; knowing to tap the Forest and *keep* the
Island up for the counterspell in hand is the advice a beginner never gets.

Structurally this is bipartite matching. Each coloured symbol must be met by a
source that makes one of its colours; generic symbols accept anything, so once
the coloured ones are matched it is only a question of how many sources remain.
With a dozen sources the search space is small enough to enumerate exactly,
which is worth far more than being clever -- the answer is exact, and every
payment can be ranked rather than only the first one found.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from mtgcoach.core.manacost import ManaCost, ManaSource


@dataclass(frozen=True, slots=True)
class Payment:
    """One way to pay a cost: which sources to tap, and what is left untapped."""

    tapped: tuple[str, ...]
    spare: tuple[str, ...]

    @property
    def count(self) -> int:
        """How many sources this payment uses."""
        return len(self.tapped)


def _colour_assignments(
    symbols: Sequence[frozenset[str]],
    sources: Sequence[ManaSource],
    used: frozenset[int],
) -> Iterable[frozenset[int]]:
    """Every set of sources that can meet the coloured symbols, one per symbol."""
    if not symbols:
        yield used
        return
    head, rest = symbols[0], symbols[1:]
    for index, source in enumerate(sources):
        if index in used or not source.can_pay(head):
            continue
        yield from _colour_assignments(rest, sources, used | {index})


def payments(cost: ManaCost, sources: Sequence[ManaSource]) -> tuple[Payment, ...]:
    """Every distinct way to pay ``cost`` from ``sources``, best first.

    "Best" means fewest sources tapped, then most colours left untapped -- a
    payment that leaves a Swamp and an Island up is more useful than one leaving
    two Swamps, because it keeps more of your hand live.

    An ``{X}`` cost is treated as X=0; the caller decides what to pay for X and
    asks again with it folded into the generic part.
    """
    if cost.colorless:
        # A {C} symbol needs specifically colourless mana, which no source in
        # the box makes. Refusing beats quietly treating it as generic.
        return ()

    seen: set[tuple[str, ...]] = set()
    found: list[Payment] = []
    for coloured in _colour_assignments(cost.symbols, sources, frozenset()):
        spare_indices = [i for i in range(len(sources)) if i not in coloured]
        if len(spare_indices) < cost.generic:
            continue
        for generic in _combinations(spare_indices, cost.generic):
            used = coloured | frozenset(generic)
            key = tuple(sorted(sources[i].instance_id for i in used))
            if key in seen:
                continue
            seen.add(key)
            found.append(
                Payment(
                    tapped=key,
                    spare=tuple(
                        sorted(sources[i].instance_id for i in range(len(sources)) if i not in used)
                    ),
                )
            )
    found.sort(key=lambda p: (p.count, -_flexibility(p, sources)))
    return tuple(found)


def can_pay(cost: ManaCost, sources: Sequence[ManaSource]) -> bool:
    """Whether the cost can be paid at all."""
    return bool(payments(cost, sources))


def _combinations(items: Sequence[int], size: int) -> Iterable[tuple[int, ...]]:
    if size == 0:
        yield ()
        return
    for position in range(len(items) - size + 1):
        for rest in _combinations(items[position + 1 :], size - 1):
            yield (items[position], *rest)


def _flexibility(payment: Payment, sources: Sequence[ManaSource]) -> int:
    """How many distinct colours the untapped sources could still make."""
    by_id = {s.instance_id: s for s in sources}
    return len(frozenset[str]().union(*(by_id[i].produces for i in payment.spare), frozenset()))
