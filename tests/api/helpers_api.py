"""A server built out of cards written in the test, not read from a disk."""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers_coach import taps_for

from helpers import facts
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import Catalogue

if TYPE_CHECKING:
    from collections.abc import Mapping

    from fastapi import FastAPI

FOREST = facts("Forest", land=True)
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
GROWTH = facts("Giant Growth", "{G}", instant=True)

#: A catalogue small enough to read, with one card of each kind that matters.
CATALOGUE = Catalogue(
    cards={"Forest": FOREST, "Bear": BEAR, "Growth": GROWTH},
    rules={"Forest": (taps_for("{G}"),)},
)

#: The opening seven are the first seven, so this is what a test will be
#: holding: five Forests, a Bear and a trick. Enough to play a land, cast the
#: creature next turn, and keep a card that cannot be cast yet.
GREEN = (
    "Forest",
    "Forest",
    "Forest",
    "Bear",
    "Forest",
    "Growth",
    "Forest",
    "Forest",
    "Forest",
    "Bear",
)
DECKS: Mapping[str, tuple[str, ...]] = {"green": GREEN, "other": GREEN}


def server(decks: Mapping[str, tuple[str, ...]] | None = None) -> FastAPI:
    """An app with the small catalogue and two identical decks."""
    return create_app(CATALOGUE, DECKS if decks is None else decks)
