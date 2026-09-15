"""The stack: one ordered zone, shared by both players.

It was a tuple on each ``PlayerState``, and ``ZoneName`` said why -- a spell's
card returns to *its owner's* graveyard (CR 608.2m), so filing it under its
owner is where it has to come back from, and it kept card conservation
checkable per player, which is the invariant a self-play season checks on every
one of a hundred thousand events. That docstring also said what the
arrangement did not model: the order of two spells on the stack at once, which
nothing could produce yet because it needs priority.

Priority produces it, and the old arrangement was then wrong rather than
merely incomplete. Two spells filed under two players are two orders with no
way to compare them, so the engine let the spell cast *first* resolve first --
the exact opposite of CR 405.5, and the whole of what answering a spell means.

So the order lives here, once, and each object carries its controller as a
field (CR 405.4) rather than being filed in a collection per player. Both of
the old reasons survive that: ``GameState.cards_of`` reads the controller to
answer a per-player question about a shared zone, and resolution puts the card
into that player's graveyard.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import InstanceId, PlayerId


@dataclass(frozen=True, slots=True)
class StackObject:
    """One spell waiting to resolve (CR 405.1), and whose it is.

    ``controller`` is the player who cast it (CR 405.4). In this engine that is
    also the card's *owner*: a spell only ever arrives here from its own
    owner's hand, so "its owner's graveyard" (CR 608.2m) and "the controller's
    graveyard" name the same zone. An effect that makes the two differ is not
    modelled and nothing in a two-player game of the Beginner Box produces one.

    A spell, and only a spell. An activated or triggered ability goes on the
    stack in the rules too (CR 602.2a, CR 603.3), with no card attached, and
    this engine has no ability objects to put there. That gap is disclosed
    where a player can read it; see ``disclosure``.
    """

    card: CardInstance
    controller: PlayerId

    @property
    def instance_id(self) -> InstanceId:
        """Which physical card this is, so a caller need not reach through."""
        return self.card.instance_id


def top(stack: Sequence[StackObject]) -> StackObject | None:
    """The object that resolves next, or None when the stack is empty.

    The last one added, because each new object is put on top of everything
    already there (CR 405.2) and it is the top that resolves (CR 405.5). The
    tuple is kept bottom-first so that "put on top" is an append -- the same
    order the wire sends, and the client reverses it for display, because the
    thing that happens next belongs at the top of a list a person reads.
    """
    return stack[-1] if stack else None


def find(stack: Sequence[StackObject], instance_id: InstanceId) -> StackObject | None:
    """The object for this card wherever it sits in the stack, or None.

    Separate from ``top`` so that a caller can tell "that spell is not on the
    stack" from "that spell is not the top of it". They are different mistakes
    and a player making either deserves to be told which.
    """
    return next((one for one in stack if one.instance_id == instance_id), None)


def controlled_by(stack: Sequence[StackObject], player_id: PlayerId) -> Iterator[CardInstance]:
    """Every card on the stack belonging to one player.

    The shared zone's answer to a per-player question. ``PlayerState.cards``
    used to yield these because the stack was one of its fields; the invariant
    that no event changes how many cards a player has is worth more than that
    convenience, so ``GameState.cards_of`` composes the two instead.
    """
    for one in stack:
        if one.controller == player_id:
            yield one.card
