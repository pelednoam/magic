"""One player's half of the game state."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING, assert_never

from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import InstanceId
    from mtgcoach.core.permanents import Permanent

#: Starting life in a two-player game (CR 103.3).
STARTING_LIFE = 20

#: Cards drawn for an opening hand (CR 103.5).
OPENING_HAND_SIZE = 7

#: Land drops per turn without an effect that grants more (CR 305.2).
MAX_LAND_DROPS_PER_TURN = 1


@dataclass(frozen=True, slots=True)
class PlayerState:
    """Everything belonging to one player.

    This is the *true* state, including cards the opponent cannot see. Hiding
    information is a presentation concern: a view layer redacts a player's
    library and hand before the state reaches the other player's screen. Keeping
    the engine fully informed is what makes card conservation checkable and
    keeps every legality question answerable without a special case for "we do
    not know".
    """

    library: tuple[CardInstance, ...]
    hand: tuple[CardInstance, ...]
    battlefield: tuple[Permanent, ...]
    graveyard: tuple[CardInstance, ...]
    exile: tuple[CardInstance, ...]
    life: int = STARTING_LIFE
    lands_played_this_turn: int = 0

    def cards(self) -> Iterator[CardInstance]:
        """Every card this player owns, in every zone.

        The basis of the conservation invariant: no event may change how many
        cards this yields.
        """
        yield from self.library
        yield from self.hand
        yield from (permanent.card for permanent in self.battlefield)
        yield from self.graveyard
        yield from self.exile

    def zone(self, name: ZoneName) -> tuple[CardInstance, ...]:
        """Return the cards in one zone, battlefield permanents included."""
        match name:
            case ZoneName.LIBRARY:
                return self.library
            case ZoneName.HAND:
                return self.hand
            case ZoneName.BATTLEFIELD:
                return tuple(permanent.card for permanent in self.battlefield)
            case ZoneName.GRAVEYARD:
                return self.graveyard
            case ZoneName.EXILE:
                return self.exile
        assert_never(name)

    def find(self, name: ZoneName, instance_id: InstanceId) -> CardInstance | None:
        """Return the card with ``instance_id`` in ``name``, or None."""
        for card in self.zone(name):
            if card.instance_id == instance_id:
                return card
        return None

    def begin_turn(self) -> PlayerState:
        """Apply the turn-based actions that happen as this player's turn begins.

        Three separate rules that happen to coincide at the untap step, and that
        an earlier docstring conflated under a single citation:

        - Every permanent untaps (CR 502.2).
        - Summoning sickness lifts. CR 302.6 is a continuous condition, not an
          action the untap step performs; clearing a flag here is a modelling
          shortcut, correct because this is the moment the condition becomes
          true. See ``Permanent.settle``.
        - The land drop is one per turn (CR 305.2), so it resets.
        """
        return replace(
            self,
            battlefield=tuple(p.untap().settle() for p in self.battlefield),
            lands_played_this_turn=0,
        )
