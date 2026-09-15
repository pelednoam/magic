"""The zones a card can occupy."""

from __future__ import annotations

from enum import StrEnum


class ZoneName(StrEnum):
    """A zone within one player's half of the game.

    The command zone is shared and does not exist here; it arrives with
    commanders, which this project does not play.

    **The stack is not here, and used to be.** It was a member of this enum and
    a tuple on each ``PlayerState``, filed under the owner because that is
    where a resolving spell's card has to come back from (CR 608.2m) and
    because it kept card conservation checkable per player. This docstring said
    so, and said what the arrangement did not model: the order of two spells on
    the stack at once, which nothing could produce until the engine had
    priority (CR 117). It has priority now, so the stack is a single ordered
    field on ``GameState`` and each object on it names its own controller --
    see ``stack``, which keeps both of the original reasons and adds the order.

    What is left here is exactly the zones that belong to one player. A caller
    can move a card between any two of them; putting a card on the stack is
    casting it, which needs a controller and a payment, and is not a move.
    """

    LIBRARY = "library"
    HAND = "hand"
    BATTLEFIELD = "battlefield"
    GRAVEYARD = "graveyard"
    EXILE = "exile"
