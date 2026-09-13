"""Resolving one combat: who dies, what gets through, what it costs.

Damage happens in up to two steps. Creatures with first or double strike deal
theirs first (CR 510.5), and anything that dies then never deals its own -- which
is the single most common surprise for a new player, and the reason first strike
is worth more than its stats suggest.

Within a step all damage is simultaneous, so a creature that will die still
deals its damage. That too is unintuitive and worth getting right: trading is a
real play, not an accident.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from mtgcoach.core.ids import InstanceId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.model import Blocks, Creature


@dataclass(frozen=True, slots=True)
class Outcome:
    """What one attack would do."""

    damage_to_defender: int = 0
    attackers_lost: tuple[str, ...] = ()
    blockers_lost: tuple[str, ...] = ()
    life_gained: int = 0
    life_lost_by_defender: int = 0


@dataclass
class _Board:
    """Damage marked so far, and who has already died."""

    marked: dict[InstanceId, int] = field(default_factory=dict[InstanceId, int])
    lethal: set[InstanceId] = field(default_factory=set[InstanceId])
    to_defender: int = 0
    lifelink: int = 0

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
class _Hit:
    """One creature's damage to one target, decided before any is applied."""

    target: InstanceId
    amount: int
    deathtouch: bool


def _attacker_hits(
    attacker: Creature, blockers: Sequence[Creature], board: _Board
) -> tuple[list[_Hit], int]:
    """How an attacker splits its damage, and how much tramples through."""
    hits: list[_Hit] = []
    if not blockers:
        return hits, attacker.power

    remaining = attacker.power
    deathtouch = attacker.has("Deathtouch")
    tramples = attacker.has("Trample")
    for blocker in blockers:
        if remaining <= 0:
            break
        # Deathtouch makes one point lethal, so the rest may trample over.
        already = board.marked.get(blocker.instance_id, 0)
        needed = 1 if deathtouch else max(blocker.toughness - already, 0)
        assigned = min(remaining, needed) if tramples else remaining
        hits.append(_Hit(blocker.instance_id, assigned, deathtouch=deathtouch))
        remaining -= assigned
    return hits, remaining if tramples else 0


def _step_damage(
    attackers: Sequence[Creature], blocks: Blocks, board: _Board, *, first: bool
) -> None:
    """Deal one damage step's damage, all of it at once.

    Gathered before any of it lands, because damage within a step is
    simultaneous (CR 510.2): a creature that will die still deals its own.

    The two directions are collected independently. Nesting the blockers' damage
    inside the attackers' loop meant that when a first-striker skipped the
    regular step, so did everything blocking it -- a 2/2 first striker walked
    away from a 5/5.
    """
    hits: list[_Hit] = []
    trample_through = 0
    lifelink = 0

    for attacker in attackers:
        if not _deals(attacker, first=first) or board.is_dead(attacker):
            continue
        blockers = [b for b in blocks.on(attacker) if not board.is_dead(b)]
        attacker_hits, spilled = _attacker_hits(attacker, blockers, board)
        hits.extend(attacker_hits)
        trample_through += spilled
        if attacker.has("Lifelink"):
            lifelink += sum(h.amount for h in attacker_hits) + spilled

    for attacker in attackers:
        for blocker in blocks.on(attacker):
            if not _deals(blocker, first=first) or board.is_dead(blocker):
                continue
            hits.append(
                _Hit(
                    attacker.instance_id,
                    blocker.power,
                    deathtouch=blocker.has("Deathtouch"),
                )
            )

    everyone = {c.instance_id: c for c in (*attackers, *blocks.blockers)}
    for hit in hits:
        board.hit(everyone[hit.target], hit.amount, deathtouch=hit.deathtouch)
    board.to_defender += trample_through
    board.lifelink += lifelink


def _deals(creature: Creature, *, first: bool) -> bool:
    """Whether this creature deals damage in this step."""
    return creature.deals_first_strike_damage if first else creature.deals_regular_damage


def resolve(attackers: Sequence[Creature], blocks: Blocks) -> Outcome:
    """Work out what an attack would do, if it were made and blocked this way."""
    board = _Board()
    for first in (True, False):
        _step_damage(attackers, blocks, board, first=first)
    return Outcome(
        damage_to_defender=board.to_defender,
        attackers_lost=tuple(sorted(a.name for a in attackers if board.is_dead(a))),
        blockers_lost=tuple(sorted(b.name for b in blocks.blockers if board.is_dead(b))),
        life_gained=board.lifelink,
        life_lost_by_defender=board.to_defender,
    )
