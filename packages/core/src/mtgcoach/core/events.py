"""Everything that can change the game state.

A closed union matched with ``assert_never`` in ``reduce``: adding a member here
fails the type check at every site that must handle it, which is what keeps the
reducer honest as the engine grows.

Events are the durable record. State is derived by folding them over the
starting position, so the log is the game -- undo, replay and end-of-game review
all fall out of it rather than being built separately.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.ids import InstanceId, PlayerId
    from mtgcoach.core.zones import ZoneName


@dataclass(frozen=True, slots=True)
class AdvanceStep:
    """Move to the next step, wrapping into the next player's turn."""


@dataclass(frozen=True, slots=True)
class DrawCard:
    """Move the top card of a library into its owner's hand."""

    player: PlayerId


@dataclass(frozen=True, slots=True)
class PlayLand:
    """Spend the turn's land drop to put a card from hand onto the battlefield.

    The reducer checks that the card is in hand and that the land drop is
    unspent. It cannot check that the card is a *land*: ``core`` holds no card
    data by design, so that check arrives with the card database. Until then a
    caller can play any card in hand as its land for the turn.
    """

    player: PlayerId
    instance_id: InstanceId


@dataclass(frozen=True, slots=True)
class SetTapped:
    """Tap or untap one permanent."""

    player: PlayerId
    instance_id: InstanceId
    tapped: bool


@dataclass(frozen=True, slots=True)
class MoveCard:
    """Move one card between two of a player's zones, unconditionally.

    The unchecked primitive that effects are built from, not a player action.
    It bypasses the land drop deliberately: plenty of effects put a permanent
    onto the battlefield without spending one. Player actions that carry a cost
    or a limit get their own event, as ``PlayLand`` does.
    """

    player: PlayerId
    instance_id: InstanceId
    to: ZoneName


@dataclass(frozen=True, slots=True)
class ChangeLife:
    """Add to or subtract from a player's life total."""

    player: PlayerId
    amount: int


type Event = AdvanceStep | DrawCard | PlayLand | SetTapped | MoveCard | ChangeLife
