"""How the coach asks about a card, without knowing where cards come from.

``core`` holds no card data and ``coach`` holds none either: both take what
they need through this Protocol, and ``carddata`` supplies it. That is what
keeps the whole engine testable against a handful of cards written inline, and
what will keep a second set from needing a second coach.

The lookups return ``None`` rather than raising, because a card the fixture
does not model is the ordinary case, not an error. Foundations is 52% modelled;
a coach that fell over on the other half would be useless at the table. What it
must never do is guess -- an unmodelled card is *reported* as unmodelled, and
the player is told the coach cannot speak for it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.ids import OracleId


class CardLookup(Protocol):
    """What the coach needs to know about a card to reason about it."""

    def facts(self, oracle_id: OracleId) -> CardFacts | None:
        """The engine's view of the card, or None if it is not known."""
        ...

    def abilities(self, oracle_id: OracleId) -> Sequence[Ability]:
        """The card's modelled abilities, empty when there are none or it is unknown."""
        ...

    def name(self, oracle_id: OracleId) -> str:
        """The printed name, falling back to the identifier when unknown.

        The fallback is deliberate: a raw identifier tells the player something
        true -- this is a card the coach cannot name -- which is better than an
        empty space they will read as a bug.
        """
        ...

    def modelled(self, oracle_id: OracleId) -> bool:
        """Whether the engine can speak for this card completely.

        Not the same as ``abilities()`` being non-empty, and that difference is
        the whole point: an empty list means *either* "a vanilla creature, fully
        understood" *or* "this card is not in the fixture at all", and a coach
        that cannot tell those apart will give confident advice about a card it
        has never seen.

        Nor is it the same as ``facts()`` being present. 59 of the Beginner
        Box's 124 cards are in the fixture with an ``UnmodeledAbility`` in them
        -- the extractor could name what the card does but not express it -- and
        those have perfectly good facts. They are exactly the cards the player
        has to read for themselves.
        """
        ...
