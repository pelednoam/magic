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

from mtgcoach.core.combat.assignments import (
    block_assignments,
    damage_orders,
    identity,
)
from mtgcoach.core.combat.budget import check_defence_size, check_plan_size
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import UNKNOWN_STATS, Blocks

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.board import Outcome
    from mtgcoach.core.combat.model import Creature

#: How a candidate outcome is ranked. The last term is a total order over the
#: creatures involved, so that a tie is never broken by list position.
type _Key = tuple[int, int, int, int, tuple[tuple[str, ...], tuple[str, ...]]]


@dataclass(frozen=True, slots=True)
class Plan:
    """One attack, and what the defender's best answer does to it."""

    attackers: tuple[Creature, ...]
    outcome: Outcome
    defender_life_after: int

    @property
    def names(self) -> tuple[str, ...]:
        """The attackers' names, for showing a player."""
        return tuple(c.name for c in self.attackers)

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


def _best_for_attacker(
    attackers: Sequence[Creature], blocks: Blocks, defender_life: int
) -> Outcome:
    """The outcome when the attacker assigns damage as well as they can.

    Mirror image of ``best_defence``: win if you can, then kill more than you
    lose, then push damage through -- and, where those tie, kill the bigger
    creature. That last term is what makes the answer independent of the order
    the caller happened to pass the blockers in.
    """
    best: Outcome | None = None
    best_key: _Key | None = None
    for order in damage_orders(attackers, blocks):
        outcome = resolve(attackers, order)
        key = (
            0 if outcome.defender_life_after(defender_life) <= 0 else 1,
            len(outcome.attackers_lost) - len(outcome.blockers_lost),
            -outcome.damage_to_defender,
            -sum(c.power + c.toughness for c in outcome.blockers_lost),
            identity(outcome),
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
    check_defence_size(attackers, blockers)
    best: Outcome | None = None
    best_key: _Key | None = None
    for blocks in block_assignments(attackers, blockers):
        outcome = _best_for_attacker(attackers, blocks, defender_life)
        key = (
            1 if outcome.defender_life_after(defender_life) <= 0 else 0,
            len(outcome.blockers_lost) - len(outcome.attackers_lost),
            outcome.damage_to_defender,
            sum(c.power + c.toughness for c in outcome.blockers_lost),
            identity(outcome),
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
    check_plan_size(attackers, blockers)

    found: list[Plan] = []
    for size in range(len(attackers) + 1):
        for chosen in itertools.combinations(attackers, size):
            outcome = best_defence(chosen, blockers, defender_life)
            found.append(
                Plan(
                    attackers=chosen,
                    outcome=outcome,
                    defender_life_after=outcome.defender_life_after(defender_life),
                )
            )
    found.sort(key=lambda p: (not p.is_lethal, -p.value, len(p.attackers)))
    return tuple(found)
