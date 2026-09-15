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
    """End the current step, wrapping into the next player's turn.

    A consequence now, not a request. A step in which players receive priority
    ends when the stack is empty *and* every player has passed in succession
    (CR 500.2) -- so this is refused until that is true, and the untap and
    cleanup steps, where nobody receives priority, end when their own actions
    are done (CR 500.3). It used to be accepted whenever the stack happened to
    be empty, which is the half of CR 500.2 the rule explicitly warns against:
    each player gets a chance to add something to the stack first, and a client
    could advance straight past the other player's only window.
    """


@dataclass(frozen=True, slots=True)
class PassPriority:
    """One player declines to act, handing priority on (CR 117.3d).

    The event that was missing, and the reason the app could cast a spell and
    resolve it in the same breath: with nothing recording who may act, there
    was no way to *not* act, so there was no moment for the other player to
    answer a spell in. A step ending and the top of the stack resolving are
    both consequences of everybody passing (CR 117.4), and they are now
    consequences of this event rather than things a client simply asks for.

    Carries the player, so that a pass by the seat that does not hold priority
    is refused rather than silently accepted. One device must not be able to
    pass on the other seat's behalf -- that is the shortcut the app took by
    resolving its own spell, dressed as a rule.
    """

    player: PlayerId


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

    Casting and resolving are separate events, because they are two things that
    happen at different times with a gap between them in which the game can
    change. A single "play this card" event modelled the gap away, and the
    board it left was wrong in a way anybody could see: an Opt sat on the
    battlefield, because the only way to play a non-land was to move it there.

    The gap is no longer empty. This takes priority to do (CR 117.1a) and hands
    it straight back (CR 117.3c), and the spell does not resolve until every
    player has passed in succession (CR 117.4) -- which is the moment the other
    player spends deciding whether to answer it.

    One event, including the payment, because casting is one action. CR 601.2
    runs from announcing the spell to paying its costs without stopping: no
    player receives priority part-way through, and a spell half-cast is not a
    state the game can be in. Tapping the lands as a separate event first was
    both wrong about that and broken -- the mana was gone by the time anything
    checked whether it covered the cost, so every paid cast over HTTP was
    refused, and a cast sent with no taps at all was free.

    The reducer checks that the card is in hand and that every source named is
    an untapped permanent of that player, then taps them. It cannot check that
    they *cover the cost* -- ``core`` holds no card data by design, so it does
    not know what the spell costs or what a Forest makes. ``api.guard`` does,
    and refuses the cast before a single land is tapped.
    """

    player: PlayerId
    instance_id: InstanceId
    #: The permanents tapped to pay for it (CR 601.2h). Empty for a spell that
    #: costs nothing, and for a recording made before casting took a payment.
    payment: tuple[InstanceId, ...] = ()


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
    AdvanceStep
    | PassPriority
    | DrawCard
    | PlayLand
    | CastSpell
    | ResolveSpell
    | SetTapped
    | MoveCard
    | ChangeLife
)
