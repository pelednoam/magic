"""Which attacks are worth making.

Enumerating every attack and, for each, the defender's best answer, and within
that the attacker's best assignment of damage. Exact, because exact is what
makes the advice trustworthy: a heuristic that is right most of the time teaches
a child the wrong lesson the rest of the time.

The defender is assumed to block well. That is the honest assumption to show a
beginner: an attack that only works if the opponent misplays is not a good
attack, it is a gamble, and the point of the coach is to tell them which is which.

The search is exponential in *both* board dimensions, so both are bounded and
the bound is a refusal rather than an approximation -- see ``budget``.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.core.combat.budget import check_size
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import MENACE_MINIMUM, UNKNOWN_STATS, Blocks, can_block

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from mtgcoach.core.combat.board import Outcome
    from mtgcoach.core.combat.model import Creature
    from mtgcoach.core.ids import InstanceId

#: Every blocker count a creature with menace forbids: one, and only one.
_ILLEGAL_MENACE_BLOCKS = frozenset(range(1, MENACE_MINIMUM))


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


def _menace_respected(
    attackers: Sequence[Creature], by_attacker: dict[InstanceId, list[Creature]]
) -> bool:
    """CR 702.111a: a creature with menace needs two blockers or none."""
    return all(
        len(by_attacker.get(attacker.instance_id, [])) not in _ILLEGAL_MENACE_BLOCKS
        for attacker in attackers
        if attacker.has("Menace")
    )


def _damage_orders(attackers: Sequence[Creature], blocks: Blocks) -> Iterator[Blocks]:
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


def _best_for_attacker(
    attackers: Sequence[Creature], blocks: Blocks, defender_life: int
) -> Outcome:
    """The outcome when the attacker assigns damage as well as they can.

    Mirror image of ``best_defence``: win if you can, then kill more than you
    lose, then push damage through -- and, where those tie, kill the bigger
    creature. That last term is what makes the answer independent of the order
    the caller happened to pass the blockers in.
    """
    worth = {b.name: b.power + b.toughness for b in blocks.blockers}
    best: Outcome | None = None
    best_key: tuple[int, int, int, int] | None = None
    for order in _damage_orders(attackers, blocks):
        outcome = resolve(attackers, order)
        key = (
            0 if outcome.life_swing_against(defender_life) <= 0 else 1,
            len(outcome.attackers_lost) - len(outcome.blockers_lost),
            -outcome.damage_to_defender,
            -sum(worth[name] for name in outcome.blockers_lost),
        )
        if best_key is None or key < best_key:
            best, best_key = outcome, key
    return best if best is not None else resolve(attackers, blocks)


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

    Raises:
        TooManyCombinationsError: If this board is too large to search exactly.
    """
    check_size(attackers, blockers)
    best: Outcome | None = None
    best_key: tuple[int, int, int] | None = None
    for blocks in _block_assignments(attackers, blockers):
        outcome = _best_for_attacker(attackers, blocks, defender_life)
        key = (
            1 if outcome.life_swing_against(defender_life) <= 0 else 0,
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
        ValueError: If a creature has no fixed power or toughness, or the board
            is too large to search exactly. Both are cases where a confident
            answer would be a guess.
    """
    unknown = [c.name for c in (*attackers, *blockers) if not c.has_fixed_stats]
    if unknown:
        msg = f"cannot evaluate combat: {', '.join(sorted(unknown))} {UNKNOWN_STATS}"
        raise ValueError(msg)
    check_size(attackers, blockers)

    found: list[Plan] = []
    for size in range(len(attackers) + 1):
        for chosen in itertools.combinations(attackers, size):
            outcome = best_defence(chosen, blockers, defender_life)
            found.append(
                Plan(
                    attackers=tuple(sorted(c.name for c in chosen)),
                    outcome=outcome,
                    defender_life_after=outcome.life_swing_against(defender_life),
                )
            )
    found.sort(key=lambda p: (not p.is_lethal, -p.value, len(p.attackers)))
    return tuple(found)
