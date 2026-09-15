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

    def not_carried_out(self, oracle_id: OracleId) -> tuple[str, ...]:
        """What the engine will not do if this card is played, in words.

        Empty when it will do all of it. See ``api.cards.Catalogue`` for why
        this cannot be answered from the abilities alone.
        """
        ...

    def text(self, oracle_id: OracleId) -> str:
        """The card's printed rules text, verbatim, empty when it is unknown.

        A different question from ``abilities``, and the two must not be
        confused: that is the engine's *model* of the card, which exists to be
        carried out, and this is the printing, which exists to be quoted. A
        rules question used to reach the model with the model's own summary --
        name, printed statistics, keywords, and a flag saying rules text
        existed somewhere -- so "does my Dazzling Angel gain me life when I
        play a creature?" arrived without the sentence "Whenever another
        creature you control enters, you gain 1 life" anywhere in it, and was
        answered from whatever the model remembered about the card.

        Empty rather than raising, like the rest of this Protocol. And empty
        rather than the ability model rendered back into prose: a paraphrase of
        a card is the same failure as a paraphrase of a rule, and this project
        exists to stop the second one.
        """
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
