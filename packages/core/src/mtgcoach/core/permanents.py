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

    Counters and attachments are deliberately absent: nothing in M1 can create
    one, and a field no event can set is a field no test can cover. They arrive
    with the effect model in M4.
    """

    card: CardInstance
    tapped: bool = False
    summoning_sick: bool = True

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
