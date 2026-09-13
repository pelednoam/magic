"""The colours in a mana cost.

CR 105.2: a card's colour is determined by its mana cost. That matters here
because Scryfall does not give every face a ``colors`` field -- an adventure
card's faces carry none at all -- so a face that declares no colours is not
colourless, it is undeclared, and the cost is what settles it.

This is deliberately only the colour question. Paying a cost is the mana
solver's job in M4, and it will need a fuller parse than this.
"""

from __future__ import annotations

import re
from typing import Final

#: The five colours, as Scryfall and the rules spell them.
COLORS: Final[frozenset[str]] = frozenset("WUBRG")

#: Symbols inside braces. Hybrid ({W/U}) and Phyrexian ({W/P}) both mention
#: their colours, and a symbol mentioning two colours makes the card both, so
#: scanning for colour letters inside braces gets every case right without
#: enumerating the symbol grammar.
_SYMBOL = re.compile(r"\{([^{}]*)\}")


def colors_in(mana_cost: str) -> frozenset[str]:
    """Return the colours a mana cost makes its card.

    Generic ({2}), colourless ({C}), snow ({S}) and variable ({X}) costs
    contribute no colour, which falls out of simply looking for colour letters.
    """
    found = {
        letter for symbol in _SYMBOL.findall(mana_cost) for letter in symbol if letter in COLORS
    }
    return frozenset(found)
