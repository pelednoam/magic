"""Turn structure: the steps of a turn and the order they occur in.

Set-agnostic and rules-stable -- the turn structure has not changed since 1999
and is identical for every set, which is why it lives in ``core`` with no
reference to any card data.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Final


class Step(StrEnum):
    """One step or phase of a turn, in the order defined by CR 500-514."""

    UNTAP = "untap"
    UPKEEP = "upkeep"
    DRAW = "draw"
    PRECOMBAT_MAIN = "precombat_main"
    BEGIN_COMBAT = "begin_combat"
    DECLARE_ATTACKERS = "declare_attackers"
    DECLARE_BLOCKERS = "declare_blockers"
    COMBAT_DAMAGE = "combat_damage"
    END_COMBAT = "end_combat"
    POSTCOMBAT_MAIN = "postcombat_main"
    END_STEP = "end_step"
    CLEANUP = "cleanup"


#: Every step exactly once, in turn order. ``test_steps`` asserts this covers
#: the whole enum, so adding a member without ordering it fails the suite.
TURN_ORDER: Final[tuple[Step, ...]] = (
    Step.UNTAP,
    Step.UPKEEP,
    Step.DRAW,
    Step.PRECOMBAT_MAIN,
    Step.BEGIN_COMBAT,
    Step.DECLARE_ATTACKERS,
    Step.DECLARE_BLOCKERS,
    Step.COMBAT_DAMAGE,
    Step.END_COMBAT,
    Step.POSTCOMBAT_MAIN,
    Step.END_STEP,
    Step.CLEANUP,
)

_MAIN_PHASES: Final[frozenset[Step]] = frozenset({Step.PRECOMBAT_MAIN, Step.POSTCOMBAT_MAIN})

_COMBAT_STEPS: Final[frozenset[Step]] = frozenset(
    {
        Step.BEGIN_COMBAT,
        Step.DECLARE_ATTACKERS,
        Step.DECLARE_BLOCKERS,
        Step.COMBAT_DAMAGE,
        Step.END_COMBAT,
    }
)


def next_step(step: Step) -> Step:
    """Return the step following ``step``, wrapping cleanup back to untap.

    Wrapping is deliberate: the caller advances the turn counter and the active
    player when it observes the wrap, rather than this function knowing about
    either.
    """
    index = TURN_ORDER.index(step)
    return TURN_ORDER[(index + 1) % len(TURN_ORDER)]


def is_main_phase(step: Step) -> bool:
    """Whether ``step`` is one of the two main phases."""
    return step in _MAIN_PHASES


def is_combat(step: Step) -> bool:
    """Whether ``step`` is part of the combat phase."""
    return step in _COMBAT_STEPS
