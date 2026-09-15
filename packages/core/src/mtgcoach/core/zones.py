"""The zones a card can occupy."""

from __future__ import annotations

from enum import StrEnum


class ZoneName(StrEnum):
    """A zone within one player's half of the game.

    The command zone is shared and does not exist here; it arrives with
    commanders, which this project does not play.

    The stack is shared in the rules (CR 405.1) and is kept per-player here, on
    purpose. A spell's card belongs to its owner and returns to *its owner's*
    graveyard when it resolves (CR 608.2m), so filing it under its owner is
    where it has to come back from -- and it keeps card conservation checkable
    per player, which is the invariant a self-play season checks on every one of
    a hundred thousand events.

    What that does not model is the order of two spells on the stack at once.
    Nothing can produce that yet: putting a second spell on the stack means
    responding to the first, which needs priority (CR 117), and the engine has
    no priority model. When it gets one, the shared order belongs on
    ``GameState`` beside it.
    """

    LIBRARY = "library"
    HAND = "hand"
    STACK = "stack"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
