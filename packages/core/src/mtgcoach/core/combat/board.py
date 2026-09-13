"""What a combat is being tracked on, and what it comes out as.

Separated from the resolution itself so that ``damage`` reads as rules and this
reads as bookkeeping -- and because ``search`` wants ``Outcome`` without wanting
anything else.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.core.ids import InstanceId

if TYPE_CHECKING:
    from mtgcoach.core.combat.model import Creature


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one attack would do.

    Life gained is tracked per side because lifelink is not the attacker's
    privilege: a blocker with it gains the defender life, which changes whether
    an attack is lethal at all.
    """

    damage_to_defender: int = 0
    attackers_lost: tuple[str, ...] = ()
    blockers_lost: tuple[str, ...] = ()
    attacker_life_gained: int = 0
    defender_life_gained: int = 0

    def life_swing_against(self, defender_life: int) -> int:
        """The defender's life total after this attack."""
        return defender_life - self.damage_to_defender + self.defender_life_gained


@dataclass
class Board:
    """Damage marked so far, and who has already died."""

    marked: dict[InstanceId, int] = field(default_factory=dict[InstanceId, int])
    lethal: set[InstanceId] = field(default_factory=set[InstanceId])
    to_defender: int = 0
    attacker_lifelink: int = 0
    defender_lifelink: int = 0

    def hit(self, target: Creature, amount: int, *, deathtouch: bool) -> None:
        """Mark damage on a creature, and note whether it is now lethal."""
        if amount <= 0:
            return
        self.marked[target.instance_id] = self.marked.get(target.instance_id, 0) + amount
        # CR 702.2b: any nonzero damage from a deathtouch source is lethal.
        is_lethal = deathtouch or self.marked[target.instance_id] >= target.toughness
        if is_lethal and not target.has("Indestructible"):
            self.lethal.add(target.instance_id)

    def is_dead(self, creature: Creature) -> bool:
        """Whether this creature has been dealt lethal damage."""
        return creature.instance_id in self.lethal


@dataclass(frozen=True, slots=True)
class Hit:
    """One creature's damage to one target, decided before any is applied."""

    target: InstanceId
    amount: int
    deathtouch: bool


@dataclass(frozen=True, slots=True)
class Side:
    """One side's damage for one step, before any of it is applied."""

    hits: tuple[Hit, ...]
    lifelink: int = 0
    to_defender: int = 0
