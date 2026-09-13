"""Saying which mana is missing, rather than that some is.

Split out of ``legality`` because it is a different job: that module decides
*whether*, this one decides *what to say*. Distinguishing "one short" from "no
green at all" is the difference between a player waiting a turn and a player
reading the wrong lesson, and it takes more code than the decision does.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.manacost import ManaSource


def mana_shortfall(card: CardFacts, sources: Sequence[ManaSource]) -> str:
    """Say what is missing, not merely that something is.

    Distinguishing "one short" from "no green at all" is the difference between
    a player waiting a turn and a player reading the wrong lesson.
    """
    if card.cost.colorless and not any(not source.produces for source in sources):
        # Checked, not asserted: the earlier version returned this sentence
        # whenever the cost had a {C} pip, which is a claim about the player's
        # board that the code never looked at.
        return "you have no source of colourless mana"
    available = len(sources)
    needed = card.cost.total
    if available < needed:
        short = needed - available
        return f"you need {short} more untapped source{'s' if short > 1 else ''}"
    missing = sorted(
        colour
        for colour in _required_colours(card)
        if not any(colour in source.produces for source in sources)
    )
    if missing:
        return f"you have no source of {'/'.join(missing)}"
    return "your untapped sources cannot cover that combination of colours"


def _required_colours(card: CardFacts) -> frozenset[str]:
    """The colours the cost genuinely demands.

    Not ``ManaCost.colors``, which unions a hybrid symbol's alternatives: for
    ``{W/U}{G}`` that set is ``{W, U, G}``, and a player holding a Plains and a
    Forest would be told they have no source of U. A hybrid symbol demands
    nothing in particular, so only single-colour symbols count.
    """
    return frozenset(next(iter(symbol)) for symbol in card.cost.symbols if len(symbol) == 1)
