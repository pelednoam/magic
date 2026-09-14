"""Getting from two deck names to a game that can be played.

The engine never generates randomness -- ``start_game`` says so, and it is what
makes a game a pure function of its libraries and its events. So the shuffle
happens here, from a seed, and a season that finds something can be replayed
exactly by running the same seed again. That is the difference between a
harness that finds bugs and one that finds them twice.
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING

from mtgcoach.carddata.decks import load_set_decks
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.state import start_game

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping
    from pathlib import Path

    from mtgcoach.carddata.decks import DeckEntry
    from mtgcoach.core.ids import OracleId, SetCode
    from mtgcoach.core.state import GameState

#: The two seats. Named as the API names them, so a game replayed through the
#: server reads the same.
YOU = PlayerId("you")
THEM = PlayerId("them")


def libraries(
    decks: Mapping[str, tuple[OracleId, ...]], chosen: tuple[str, str], seed: int
) -> dict[PlayerId, tuple[CardInstance, ...]]:
    """Two shuffled libraries, with every card given its own identity.

    Raises:
        KeyError: If a deck name is not one this set has.
    """
    shuffler = random.Random(seed)  # noqa: S311 - a game, not a secret
    made: dict[PlayerId, tuple[CardInstance, ...]] = {}
    for seat, name in zip((YOU, THEM), chosen, strict=True):
        cards = [
            CardInstance(instance_id=InstanceId(f"{seat}-{number}"), oracle_id=oracle)
            for number, oracle in enumerate(decks[name])
        ]
        shuffler.shuffle(cards)
        made[seat] = tuple(cards)
    return made


def table(
    data_root: Path, set_code: SetCode, names: Mapping[str, OracleId]
) -> dict[str, tuple[OracleId, ...]]:
    """Every deck this set ships that the catalogue can actually deal.

    A deck with a card the catalogue does not have is left out rather than
    dealt short. Silently skipping the missing card built a library of zero
    and failed inside ``start_game`` with "needs at least 7 cards", which says
    nothing about the real problem -- an import that did not cover this set.

    Takes the name-to-oracle map rather than looking cards up itself: the
    catalogue is built by the caller, which already had to open the database.
    """
    return {
        deck.key: dealt_deck
        for deck in load_set_decks(data_root, set_code)
        if (dealt_deck := _whole(deck.entries, names)) is not None
    }


def _whole(
    entries: Iterable[DeckEntry], names: Mapping[str, OracleId]
) -> tuple[OracleId, ...] | None:
    """The deck as oracle ids, or None if a card is missing from the catalogue."""
    made: list[OracleId] = []
    for entry in entries:
        found = names.get(entry.name)
        if found is None:
            return None
        made.extend([found] * entry.quantity)
    return tuple(made)


def dealt(
    decks: Mapping[str, tuple[OracleId, ...]], chosen: tuple[str, str], seed: int
) -> GameState:
    """A game in progress: shuffled, opening hands drawn, ``you`` on the play.

    Who is on the play alternates with the seed's parity, because "the player
    who goes first" is a real asymmetry -- they skip a draw -- and a season
    where one seat always went first would test half of it.
    """
    first = YOU if seed % 2 == 0 else THEM
    return start_game(libraries(decks, chosen, seed), first_player=first)
