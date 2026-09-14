"""The zones a card can occupy."""

from __future__ import annotations

from enum import StrEnum


class ZoneName(StrEnum):
    """A zone within one player's half of the game.

    The stack and the command zone are shared rather than per-player, and arrive
    with spell casting; every zone here belongs to exactly one player, which is
    what makes card conservation checkable per player.
    """

    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
