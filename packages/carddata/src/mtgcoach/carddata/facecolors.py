"""The colours of a printed face.

CR 105.2: a card's colour is determined by its mana cost. Scryfall does not give
every face a ``colors`` field -- an adventure card's faces carry none -- so a
face that declares none is undeclared, not colourless, and the cost settles it.

The cost grammar lives in ``core.manacost``; this only asks the colour question,
and asks it leniently. Ingestion must not fail on a cost the *solver* cannot
model: a set full of hybrid symbols should still import, with those cards simply
unplayable until the solver grows. Hence the fallback.
"""

from __future__ import annotations

import re

from mtgcoach.core.manacost import COLORS, UnsupportedCostError, parse

#: Colour letters inside braces, for costs the parser refuses.
_SYMBOL = re.compile(r"\{([^{}]*)\}")


def colors_in(mana_cost: str) -> frozenset[str]:
    """Return the colours a mana cost makes its card."""
    try:
        return parse(mana_cost).colors
    except UnsupportedCostError:
        return _scan(mana_cost)


def _scan(mana_cost: str) -> frozenset[str]:
    """Colour letters inside braces, ignoring everything else."""
    return frozenset(
        letter
        for symbol in _SYMBOL.findall(mana_cost)
        for letter in symbol.upper()
        if letter in COLORS
    )
