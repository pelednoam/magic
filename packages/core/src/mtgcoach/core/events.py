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
class CastSpell:
    """Put a card from hand onto the stack (CR 601.2a).

    Casting is two events, not one, because it is two things that happen at
    different times with a gap between them in which the game can change. A
    single "play this card" event modelled the gap away, and the board it left
    was wrong in a way anybody could see: an Opt sat on the battlefield, because
    the only way to play a non-land was to move it there.

    The reducer checks that the card is in hand. It cannot check *timing* --
    whether this is an instant, and whether it is your main phase -- because
    ``core`` holds no card data by design. ``legality.cast_reasons`` does, and
    that is what the coach and the server put in front of a player, exactly as
    with ``PlayLand``.
    """

    player: PlayerId
    instance_id: InstanceId


@dataclass(frozen=True, slots=True)
class ResolveSpell:
    """Take a spell off the stack, to where the rules send it.

    Two destinations, and they are the only two a spell resolving normally has:
    a permanent spell becomes a permanent on the battlefield (CR 608.3), and an
    instant or sorcery is put into its owner's graveyard as the final part of
    its resolution (CR 608.2m). Which of the two it is depends on the card's
    type, which ``core`` does not know -- so the caller says, as it does for
    ``MoveCard``, and the reducer refuses any other destination.

    ``player`` is the owner: a card sits on its owner's stack in this engine, so
    "into its owner's graveyard" is where it comes back to by construction. An
    owner who is not the controller is not modelled, and nothing in a
    two-player game of the Beginner Box produces one.
    """

    player: PlayerId
    instance_id: InstanceId
    to: ZoneName


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


type Event = (
    AdvanceStep | DrawCard | PlayLand | CastSpell | ResolveSpell | SetTapped | MoveCard | ChangeLife
)
