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
    """Put a land from hand onto the battlefield, using the land drop."""

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
    """Move one card between two of a player's zones."""

    player: PlayerId
    instance_id: InstanceId
    to: ZoneName


@dataclass(frozen=True, slots=True)
class ChangeLife:
    """Add to or subtract from a player's life total."""

    player: PlayerId
    amount: int


type Event = AdvanceStep | DrawCard | PlayLand | SetTapped | MoveCard | ChangeLife
