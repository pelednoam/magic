"""The pieces of a combat.

A creature in combat is its permanent plus the facts about its card, so both
travel together. Keeping them paired avoids the commonest bug in a combat
engine: resolving damage against the card's printed power while the permanent
on the table has a counter on it.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.core.ids import InstanceId

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.permanents import Permanent

#: A creature whose power is ``*`` has no fixed value. Treating it as zero would
#: make Consuming Aberration look harmless, so combat refuses to guess and the
#: caller is told the attack cannot be evaluated.
UNKNOWN_STATS = "has no fixed power or toughness"


@dataclass(frozen=True, slots=True)
class Creature:
    """A creature on the battlefield, ready to be reasoned about."""

    permanent: Permanent
    card: CardFacts

    #: Reached through two properties on every damage assignment, of which one
    #: search makes millions. Resolved once instead.
    instance_id: InstanceId = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Resolve the identifier once."""
        object.__setattr__(self, "instance_id", self.permanent.instance_id)

    @property
    def name(self) -> str:
        """The card's name."""
        return self.card.name

    @property
    def power(self) -> int:
        """Power, zero when the card has none printed."""
        return self.card.power or 0

    @property
    def toughness(self) -> int:
        """Toughness, zero when the card has none printed."""
        return self.card.toughness or 0

    @property
    def damage(self) -> int:
        """How much combat damage this creature deals.

        CR 107.1b: a negative power is treated as zero. Nothing prints one, but
        an effect can produce one, and left unclamped it dealt *negative*
        damage -- healing the defender and, with lifelink, taking life from its
        own controller.
        """
        return max(self.power, 0)

    @property
    def has_fixed_stats(self) -> bool:
        """Whether this creature's power and toughness are knowable."""
        return self.card.power is not None and self.card.toughness is not None

    def has(self, keyword: str) -> bool:
        """Whether the creature has a keyword."""
        return self.card.has(keyword)

    @property
    def deals_first_strike_damage(self) -> bool:
        """Whether it deals damage in the first-strike step (CR 510.5)."""
        return self.has("First strike") or self.has("Double strike")

    @property
    def deals_regular_damage(self) -> bool:
        """Whether it deals damage in the normal step."""
        return not self.has("First strike") or self.has("Double strike")


@dataclass(frozen=True, slots=True)
class Blocks:
    """Which blockers were assigned to which attacker."""

    by_attacker: Mapping[InstanceId, tuple[Creature, ...]] = field(
        default_factory=dict[InstanceId, tuple[Creature, ...]]
    )

    def on(self, attacker: Creature) -> tuple[Creature, ...]:
        """The creatures blocking one attacker, in damage-assignment order."""
        return self.by_attacker.get(attacker.instance_id, ())

    @property
    def blockers(self) -> tuple[Creature, ...]:
        """Every blocking creature."""
        return tuple(c for group in self.by_attacker.values() for c in group)


def can_block(blocker: Creature, attacker: Creature) -> bool:
    """Whether ``blocker`` may legally block ``attacker``.

    Covers the evasion in the Beginner Box: flying needs flying or reach to
    block (CR 702.9b), and menace needs two blockers, which is checked where the
    whole assignment is known rather than here.
    """
    if blocker.permanent.tapped:
        return False
    return not attacker.has("Flying") or blocker.has("Flying") or blocker.has("Reach")


#: Menace: a creature with it cannot be blocked except by two or more (CR 702.111a).
MENACE_MINIMUM = 2


def check_stats(*groups: Sequence[Creature]) -> None:
    """Refuse a combat containing a creature whose power is not knowable.

    Every public entry point has to ask. ``power`` returns ``self.card.power or
    0``, so a Consuming Aberration passed to a function that skipped this check
    was quietly evaluated as 0/0 -- which is the single thing the refusal exists
    to prevent, and it lived only in ``plans`` while ``best_defence`` is public
    and directly callable.

    Raises:
        ValueError: If any creature has no fixed power or toughness.
    """
    unknown = sorted(c.name for group in groups for c in group if not c.has_fixed_stats)
    if unknown:
        msg = f"cannot evaluate combat: {', '.join(unknown)} {UNKNOWN_STATS}"
        raise ValueError(msg)
