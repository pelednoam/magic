"""Which attacks are worth making.

Enumerating every attack and, for each, the defender's best answer. With eight
creatures that is 256 attacks and a small search per attack -- cheap enough to be
exact, and exact is what makes the advice trustworthy. A heuristic that is right
most of the time teaches a child the wrong lesson the rest of the time.

The defender is assumed to block well. That is the honest assumption to show a
beginner: an attack that only works if the opponent misplays is not a good
attack, it is a gamble, and the point of the coach is to tell them which is which.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import MENACE_MINIMUM, UNKNOWN_STATS, Blocks, can_block

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mtgcoach.core.combat.damage import Outcome
    from mtgcoach.core.combat.model import Creature
    from mtgcoach.core.ids import InstanceId

#: Beyond this many attackers the enumeration stops being instant. The Beginner
#: Box never fields this many, and a cap that is never reached is better than a
#: heuristic that is always approximate.
MAX_ATTACKERS = 8


@dataclass(frozen=True, slots=True)
class Plan:
    """One attack, and what the defender's best answer does to it."""

    attackers: tuple[str, ...]
    outcome: Outcome
    defender_life_after: int

    @property
    def is_lethal(self) -> bool:
        """Whether this attack wins the game outright."""
        return self.defender_life_after <= 0

    @property
    def value(self) -> int:
        """A crude score: damage through, plus creatures killed, less those lost.

        Crude on purpose. The ranking decides which plans to *show*; the
        explanation of why one is better belongs to the coach, which can read
        the whole outcome rather than one number.
        """
        return (
            self.outcome.damage_to_defender
            + 2 * len(self.outcome.blockers_lost)
            - 2 * len(self.outcome.attackers_lost)
        )


def _block_assignments(
    attackers: Sequence[Creature], blockers: Sequence[Creature]
) -> Iterator[Blocks]:
    """Every legal way the defender could block, including not blocking."""
    choices = [[None, *[a for a in attackers if can_block(blocker, a)]] for blocker in blockers]
    for combination in itertools.product(*choices) if choices else [()]:
        by_attacker: dict[InstanceId, list[Creature]] = {}
        for blocker, target in zip(blockers, combination, strict=True):
            if target is not None:
                by_attacker.setdefault(target.instance_id, []).append(blocker)
        if _menace_respected(attackers, by_attacker):
            yield Blocks({k: tuple(v) for k, v in by_attacker.items()})


#: Every blocker count a creature with menace forbids: one, and only one.
_ILLEGAL_MENACE_BLOCKS = frozenset(range(1, MENACE_MINIMUM))


def _menace_respected(
    attackers: Sequence[Creature], by_attacker: dict[InstanceId, list[Creature]]
) -> bool:
    """CR 702.111a: a creature with menace needs two blockers or none."""
    return all(
        len(by_attacker.get(attacker.instance_id, [])) not in _ILLEGAL_MENACE_BLOCKS
        for attacker in attackers
        if attacker.has("Menace")
    )


def best_defence(
    attackers: Sequence[Creature], blockers: Sequence[Creature], defender_life: int
) -> Outcome:
    """The outcome when the defender blocks as well as they can.

    Three tests in order: do not die; do not lose creatures for nothing; then
    take as little damage as possible. The middle one has to outrank damage or
    the defender chump-blocks every attack at twenty life, which would make the
    coach far too timid -- an attack that only *looks* bad because the model
    assumed a panicked opponent is exactly the advice a beginner cannot afford.

    Creature quality is not weighed: trading a 5/5 for a 1/1 with deathtouch
    counts as an even swap here. That is why a ``Plan`` carries the whole
    ``Outcome`` and not just its score.
    """
    best: Outcome | None = None
    best_key: tuple[int, int, int] | None = None
    for blocks in _block_assignments(attackers, blockers):
        outcome = resolve(attackers, blocks)
        key = (
            1 if outcome.damage_to_defender >= defender_life else 0,
            len(outcome.blockers_lost) - len(outcome.attackers_lost),
            outcome.damage_to_defender,
        )
        if best_key is None or key < best_key:
            best, best_key = outcome, key
    return best if best is not None else resolve(attackers, Blocks())


def plans(
    attackers: Sequence[Creature], blockers: Sequence[Creature], defender_life: int
) -> tuple[Plan, ...]:
    """Every attack worth considering, best first.

    Raises:
        ValueError: If a creature has no fixed power or toughness, or there are
            more attackers than the exact search will take. Both are cases where
            a confident answer would be a guess.
    """
    unknown = [c.name for c in (*attackers, *blockers) if not c.has_fixed_stats]
    if unknown:
        msg = f"cannot evaluate combat: {', '.join(sorted(unknown))} {UNKNOWN_STATS}"
        raise ValueError(msg)
    if len(attackers) > MAX_ATTACKERS:
        msg = f"cannot evaluate {len(attackers)} attackers exactly (limit {MAX_ATTACKERS})"
        raise ValueError(msg)

    found: list[Plan] = []
    for size in range(len(attackers) + 1):
        for chosen in itertools.combinations(attackers, size):
            outcome = best_defence(chosen, blockers, defender_life)
            found.append(
                Plan(
                    attackers=tuple(sorted(c.name for c in chosen)),
                    outcome=outcome,
                    defender_life_after=defender_life - outcome.damage_to_defender,
                )
            )
    found.sort(key=lambda p: (not p.is_lethal, -p.value, len(p.attackers)))
    return tuple(found)
