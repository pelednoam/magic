"""Parsing a mana cost into something payable.

A cost is written as brace-delimited symbols: ``{2}{G}{G}``. Two facts make the
representation simple. A generic symbol accepts any mana, so generic symbols
only ever need counting. And every other symbol accepts mana from *some set of
colours* -- ``{G}`` accepts green, a hybrid ``{W/U}`` accepts either -- so one
frozenset expresses both, and the solver never has to know which it is looking
at.

Costs the Beginner Box does not contain are still parsed, because set #2 will
have them, and the ones that cannot be modelled are **rejected** rather than
approximated. A cost we quietly mis-model is a coach confidently saying you can
cast something you cannot.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from mtgcoach.core.ids import InstanceId

#: The five colours.
COLORS: Final[frozenset[str]] = frozenset("WUBRG")

_SYMBOL = re.compile(r"\{([^{}]+)\}")
_GENERIC = re.compile(r"\A\d+\Z")

#: A hybrid symbol names exactly two alternatives: {W/U}.
_HYBRID_PARTS: Final = 2


class UnsupportedCostError(ValueError):
    """A cost the solver cannot reason about.

    Raised rather than guessed. ``{2/W}`` -- two generic *or* one white -- makes
    a symbol's cost depend on how it is paid, and ``{W/P}`` lets life stand in
    for mana. Neither appears in the Beginner Box, and both would need the
    solver to search over cost shapes as well as assignments.
    """


@dataclass(frozen=True, slots=True)
class ManaCost:
    """A parsed mana cost.

    ``symbols`` holds one entry per non-generic symbol: the set of colours that
    may pay it. ``{G}`` is ``{"G"}``; a hybrid ``{W/U}`` is ``{"W", "U"}``.
    """

    generic: int = 0
    symbols: tuple[frozenset[str], ...] = ()
    variable: int = 0
    colorless: int = 0

    @property
    def total(self) -> int:
        """How many mana this costs, with X counted as zero (CR 202.3b)."""
        return self.generic + len(self.symbols) + self.colorless

    @property
    def is_free(self) -> bool:
        """Whether the cost is nothing at all, as a land's is."""
        return self.total == 0 and self.variable == 0

    @property
    def colors(self) -> frozenset[str]:
        """Every colour this cost could require."""
        return frozenset[str]().union(*self.symbols) if self.symbols else frozenset()


def parse(text: str) -> ManaCost:
    """Parse a mana cost string.

    Raises:
        UnsupportedCostError: If a symbol cannot be modelled, or if the string
            contains anything outside brace-delimited symbols.
    """
    stripped = text.strip()
    if not stripped:
        return ManaCost()
    if _SYMBOL.sub("", stripped).strip():
        msg = f"{text!r} is not a mana cost"
        raise UnsupportedCostError(msg)

    generic = 0
    variable = 0
    colorless = 0
    symbols: list[frozenset[str]] = []
    for raw in _SYMBOL.findall(stripped):
        symbol = raw.upper()
        if _GENERIC.match(symbol):
            generic += int(symbol)
        elif symbol == "X":
            variable += 1
        elif symbol == "C":
            colorless += 1
        elif symbol in COLORS:
            symbols.append(frozenset({symbol}))
        else:
            symbols.append(_hybrid(symbol, text))
    return ManaCost(
        generic=generic,
        symbols=tuple(symbols),
        variable=variable,
        colorless=colorless,
    )


def _hybrid(symbol: str, original: str) -> frozenset[str]:
    parts = symbol.split("/")
    if len(parts) == _HYBRID_PARTS and all(p in COLORS for p in parts):
        return frozenset(parts)
    msg = f"{original!r} contains {{{symbol}}}, which the solver cannot model"
    raise UnsupportedCostError(msg)


@dataclass(frozen=True, slots=True)
class ManaSource:
    """Something that can produce mana, and what it can produce.

    ``produces`` is the set of colours this source could make. A Forest is
    ``{"G"}``; a dual land is two colours; a source making colourless mana has
    an empty set, which pays generic costs and nothing else.
    """

    instance_id: InstanceId
    produces: frozenset[str] = field(default_factory=frozenset[str])

    def can_pay(self, symbol: frozenset[str]) -> bool:
        """Whether this source can pay one coloured symbol."""
        return bool(self.produces & symbol)
