"""A card on the battlefield."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import InstanceId


@dataclass(frozen=True, slots=True)
class Permanent:
    """A card on the battlefield, with the state that only exists there.

    Counters and attachments are deliberately absent: nothing yet can create
    one, and a field no event can set is a field no test can cover. M4 shipped
    the effect *schema* without the casting that would put one on the table, so
    they arrive with spell casting -- the milestone that first creates one.
    """

    card: CardInstance
    tapped: bool = False
    summoning_sick: bool = True
    #: The turn this arrived on, or 0 for a permanent that was simply set up --
    #: a test fixture, or a board written out by hand. Turns start at 1, so 0
    #: can never equal the current turn and such a permanent never reads as
    #: having just arrived.
    #:
    #: Separate from ``summoning_sick``, which answers a different question.
    #: Sickness is "since your most recent turn began" and is cleared at your
    #: untap step, so a creature that arrived on the opponent's turn is still
    #: sick on yours -- correct for attacking, and a turn too wide for "its
    #: enters trigger fired". A trigger fired *when it entered*, and that is a
    #: turn number.
    entered_on_turn: int = 0

    @property
    def instance_id(self) -> InstanceId:
        """The identifier of the underlying card."""
        return self.card.instance_id

    def tap(self) -> Permanent:
        """Return a copy that is tapped."""
        return replace(self, tapped=True)

    def untap(self) -> Permanent:
        """Return a copy that is untapped."""
        return replace(self, tapped=False)

    def settle(self) -> Permanent:
        """Return a copy no longer treated as summoning sick.

        CR 302.6 phrases this as a condition -- the permanent has been under its
        controller's control *since their most recent turn began* -- rather than
        as an event. This flag is a cached answer to that question, set false at
        the moment the condition becomes true. It is stored on every permanent
        although it only matters for creatures; which permanents care is a
        legality question, not a state one.
        """
        return replace(self, summoning_sick=False)
