"""Turning a named deck into cards with identities.

Its own module because it is the one place that decides what a *copy* of a card
is. Two Forests in a decklist are one oracle id and must become two
``InstanceId``s -- the engine marks damage and tracks tapping by identity, so a
deck dealt with shared ids would be a deck whose lands tap each other.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import HTTPException
from starlette.status import HTTP_400_BAD_REQUEST

from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId

if TYPE_CHECKING:
    from collections.abc import Mapping


def library(
    decks: Mapping[str, tuple[str, ...]], player: str, deck: str
) -> tuple[CardInstance, ...]:
    """Deal one player their deck, giving every card its own identity.

    Raises:
        HTTPException: If there is no deck by that name.
    """
    if deck not in decks:
        raise HTTPException(HTTP_400_BAD_REQUEST, f"unknown deck {deck!r}")
    return tuple(
        CardInstance(InstanceId(f"{player}-{index}"), OracleId(oracle))
        for index, oracle in enumerate(decks[deck])
    )
