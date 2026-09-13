"""Whether a set of sources can cover a set of coloured symbols.

Kuhn's algorithm, and nothing else. Split out because it is the one piece of
the mana solver that is a general graph question rather than a Magic one: given
symbols on one side and sources on the other, is there a perfect matching?

The greedy answer is wrong, which is the whole reason this exists. ``{W}{U}``
from a Plains and a W/U dual: hand the dual to ``{W}`` first and ``{U}`` has
nothing left, though the payment plainly exists. Matching backs that choice out.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.manacost import ManaSource


def can_match(symbols: Sequence[frozenset[str]], chosen: Sequence[ManaSource]) -> bool:
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


def covers(symbols: Sequence[frozenset[str]], chosen: Sequence[ManaSource]) -> bool:
    """Whether ``chosen`` can meet every symbol, with the rest paying generic.

    Only the *coloured* symbols need a particular source; once each has one, the
    leftovers pay the generic part, and any source can do that. So it is enough
    to ask whether a matching exists on some subset -- which is what Kuhn's
    algorithm answers when run over all of ``chosen``.
    """
    return can_match(symbols, chosen)
