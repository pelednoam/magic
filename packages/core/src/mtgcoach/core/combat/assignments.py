"""Every legal block, and every order the attacker could assign damage in.

The two enumerations the search sits on top of. Both are pure: they say what is
*possible*, and ``search`` decides what is good.
"""

from __future__ import annotations

import itertools
from typing import TYPE_CHECKING

from mtgcoach.core.combat.model import MENACE_MINIMUM, Blocks, can_block

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mtgcoach.core.combat.board import Outcome
    from mtgcoach.core.combat.model import Creature
    from mtgcoach.core.ids import InstanceId

#: Every blocker count a creature with menace forbids: one, and only one.
_ILLEGAL_MENACE_BLOCKS = frozenset(range(1, MENACE_MINIMUM))


def block_assignments(
    attackers: Sequence[Creature], blockers: Sequence[Creature]
) -> Iterator[Blocks]:
    """Every legal way the defender could block, including not blocking."""
    choices = [[None, *[a for a in attackers if can_block(blocker, a)]] for blocker in blockers]
    for combination in itertools.product(*choices) if choices else [()]:
        by_attacker: dict[InstanceId, list[Creature]] = {}
        for blocker, target in zip(blockers, combination, strict=True):
            if target is not None:
                by_attacker.setdefault(target.instance_id, []).append(blocker)
        if menace_respected(attackers, by_attacker):
            yield Blocks({k: tuple(v) for k, v in by_attacker.items()})


def menace_respected(
    attackers: Sequence[Creature], by_attacker: dict[InstanceId, list[Creature]]
) -> bool:
    """CR 702.111b: a creature with menace needs two blockers or none."""
    return all(
        len(by_attacker.get(attacker.instance_id, [])) not in _ILLEGAL_MENACE_BLOCKS
        for attacker in attackers
        if attacker.has("Menace")
    )


def damage_orders(attackers: Sequence[Creature], blocks: Blocks) -> Iterator[Blocks]:
    """Every division of damage the attacking player could choose (CR 510.1c).

    Foundations removed damage assignment *order*: the attacker now divides its
    damage among the blockers as it likes, with lethal owed to each blocker it
    wants to kill and to all of them before anything tramples through. So the
    real choice is **which blockers to kill**, and the enumeration is over
    subsets rather than permutations.

    Both fixes at once. Permutations were the old rules, and they missed legal
    assignments -- a 4/4 that wants to kill the 3/3 and ignore the 1/1 is not
    any ordering of greedy-lethal. They were also the more expensive of the two:
    six blockers is 720 orderings and 64 subsets.

    Each subset is emitted as the blockers to kill followed by the rest, because
    that is the order greedy-lethal assignment then produces the division from.
    Duplicates are dropped: with one blocker every subset gives the same thing.
    """
    groups = [blocks.on(attacker) for attacker in attackers]
    per_attacker = [_divisions(group) for group in groups]
    for combination in itertools.product(*per_attacker) if per_attacker else [()]:
        yield Blocks(
            {
                attacker.instance_id: order
                for attacker, order in zip(attackers, combination, strict=True)
                if order
            }
        )


def _divisions(group: tuple[Creature, ...]) -> list[tuple[Creature, ...]]:
    """Each subset of ``group`` first, then the rest -- deduplicated."""
    if len(group) < 2:  # noqa: PLR2004 - nothing to choose between
        return [group]
    seen: dict[tuple[str, ...], tuple[Creature, ...]] = {}
    for size in range(len(group) + 1):
        for chosen in itertools.combinations(group, size):
            picked = frozenset(c.instance_id for c in chosen)
            order = (*chosen, *(c for c in group if c.instance_id not in picked))
            seen.setdefault(tuple(str(c.instance_id) for c in order), order)
    return list(seen.values())


def identity(outcome: Outcome) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """A total order over the creatures an outcome kills.

    Every other term in both rankings can tie -- two 0/1 chump blockers are
    worth exactly the same, and so are two 1/1 attackers -- and when they do,
    the winner used to be whichever the caller happened to list first. The coach
    then gave two different answers for one board, which a property test caught
    within a hundred examples. This makes the last tie a decision rather than an
    accident.
    """
    return (
        tuple(sorted(str(c.instance_id) for c in outcome.blockers_lost)),
        tuple(sorted(str(c.instance_id) for c in outcome.attackers_lost)),
    )
