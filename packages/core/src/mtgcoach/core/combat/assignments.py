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
    """CR 702.111a: a creature with menace needs two blockers or none."""
    return all(
        len(by_attacker.get(attacker.instance_id, [])) not in _ILLEGAL_MENACE_BLOCKS
        for attacker in attackers
        if attacker.has("Menace")
    )


def damage_orders(attackers: Sequence[Creature], blocks: Blocks) -> Iterator[Blocks]:
    """Every order the attacking player could assign damage in (CR 509.2).

    The order is the attacking player's choice. It used to be the caller's list
    order, so a 4/4 blocked by a 3/3 and a 1/1 killed whichever happened to be
    passed first, and the same board in a different order gave different advice.
    """
    groups = [blocks.on(attacker) for attacker in attackers]
    per_attacker = [
        list(itertools.permutations(group)) if len(group) > 1 else [group] for group in groups
    ]
    for combination in itertools.product(*per_attacker) if per_attacker else [()]:
        yield Blocks(
            {
                attacker.instance_id: order
                for attacker, order in zip(attackers, combination, strict=True)
                if order
            }
        )


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
