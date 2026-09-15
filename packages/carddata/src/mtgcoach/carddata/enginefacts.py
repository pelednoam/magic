"""Turning a card from the store into what the engine will take.

The missing half of M4. ``core.CardFacts`` is the narrow view the rules engine
takes of a card, and it was built only ever by the tests -- so the engine was
correct about cards that no part of the system could actually hand it. This is
the adapter, and it lives in ``carddata`` because that is the side that knows
what Scryfall's strings mean; ``core`` stays free of card data.

Everything here is per *face*. A transform card carries no top-level mana cost
at all, and an adventure card's is the joined ``{3} // {1}{B}``, so asking the
card rather than the face is how a split card ends up priced as one spell.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.facts import CardFacts
from mtgcoach.core.manacost import UnsupportedCostError, parse

if TYPE_CHECKING:
    from mtgcoach.carddata.cards import Card


class UnmodellableCardError(ValueError):
    """A card the engine cannot be given an honest view of.

    Raised rather than approximated. A cost the parser refuses is one the mana
    solver would misprice, and a coach that misprices a spell is worse than one
    that says it does not know this card.
    """


def facts_for(card: Card, face_index: int = 0) -> CardFacts:
    """The engine's view of one face of a card.

    ``keywords`` comes from the card rather than the face because Scryfall
    records them at the card level, and a keyword on either face is a keyword
    the engine should know about -- over-reporting a keyword the back face has
    is harmless here, because every rule that reads one also checks the type.

    Raises:
        UnmodellableCardError: If the face's mana cost cannot be modelled, or
            there is no such face.
    """
    try:
        face = card.faces[face_index]
    except IndexError as exc:
        msg = f"{card.name} has no face {face_index}"
        raise UnmodellableCardError(msg) from exc
    try:
        cost = parse(face.mana_cost)
    except UnsupportedCostError as exc:
        msg = f"{card.name}: {exc}"
        raise UnmodellableCardError(msg) from exc
    types = face.types
    return CardFacts(
        oracle_id=card.oracle_id,
        name=face.name,
        cost=cost,
        is_land=types.is_land,
        is_creature=types.is_creature,
        is_instant_speed=types.is_instant_speed,
        is_permanent=types.is_permanent,
        power=_stat(face.power),
        toughness=_stat(face.toughness),
        keywords=card.keywords,
    )


def _stat(printed: str | None) -> int | None:
    """A printed power or toughness as a number, or None when it is not one.

    ``*`` and ``1+*`` have no fixed value, and neither does an absent one. None
    is the honest answer, and every consumer in ``core`` has to say what it does
    about it -- which is why a Consuming Aberration stops a combat evaluation
    instead of being read as a 0/0.
    """
    if printed is None:
        return None
    try:
        return int(printed)
    except ValueError:
        return None
