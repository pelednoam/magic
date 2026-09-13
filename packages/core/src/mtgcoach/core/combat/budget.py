"""How big a combat the exact search will take on.

Two earlier versions of this bound got it wrong, in the same way twice: they
counted a dimension and told a story about it.

``MAX_ATTACKERS`` alone was wrong because the attack subsets are 2^A but the
block assignments are (A+1)^B -- the *blockers* are the exponent. Then bounding
``(A+1)**B`` was wrong because that is the work of a single ``best_defence``,
and ``plans`` runs one per attack subset. At the caps those two stories admitted
eight attackers against six blockers, which takes five minutes.

So the bound is measured, not reasoned about. ``resolutions_for`` counts what
the search actually does -- every block assignment, times every division of
damage the attacker could choose -- and it tracks real time to within a few
percent across every board shape tried. The constant below is that count at
roughly three seconds.

And it is a refusal, not a fallback. A coach that silently switches to a
heuristic on a big board is worse than one that says it cannot be sure, because
the player cannot tell which answer they got.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.model import Creature

#: Cheap early exits with a clearer message than the real bound gives. Neither
#: is the binding constraint -- ``MAX_RESOLUTIONS`` usually bites first.
MAX_ATTACKERS: Final = 8
MAX_BLOCKERS: Final = 6

#: How many combats the exact search will resolve before refusing. Measured at
#: about 11 microseconds each, so this is a shade over three seconds. It admits
#: eight attackers against three blockers, six against four, four against five,
#: or three against six -- past anything the Beginner Box fields, and short of
#: the boards that would make the coach appear to have hung.
MAX_RESOLUTIONS: Final = 320_000


class TooManyCombinationsError(ValueError):
    """This board is too large for the exact search.

    A ``ValueError`` because it is the same kind of refusal as a creature with
    ``*`` power: the question is well formed, and the honest answer is that a
    confident one would be a guess.
    """


def arrangements(attackers: int, blockers: int) -> int:
    """Every block, times every division of damage the attacker could choose.

    Public because it is what ``check_defence_size`` bounds, and a test that
    asserts the two counts are different has to be able to name both.

    Each blocker either sits out or blocks one attacker, and then within each
    attacker's group the attacker picks which of them to kill -- a subset. So
    for ``j`` blocking, that is ``attackers ** j`` blocks and ``2 ** j``
    subsets between them, summed over ``j``: ``(1 + 2 * attackers) ** blockers``.

    A slight over-estimate, because a group of one has only one division and the
    formula gives it two. Over-estimating is the safe direction for a bound.
    """
    return int((1 + 2 * attackers) ** blockers)


def resolutions_for(attackers: int, blockers: int) -> int:
    """How many combats ``plans`` would resolve for this board.

    One ``best_defence`` per attack subset, and within each, one ``resolve`` per
    block assignment per damage order.
    """
    return sum(
        math.comb(attackers, size) * arrangements(size, blockers) for size in range(attackers + 1)
    )


def check_defence_size(attackers: Sequence[Creature], blockers: Sequence[Creature]) -> None:
    """Refuse a single blocking search the exact method cannot finish.

    Raises:
        TooManyCombinationsError: If the board is past what will be enumerated.
    """
    _check_dimensions(attackers, blockers)
    _check(arrangements(len(attackers), len(blockers)), attackers, blockers)


def check_plan_size(attackers: Sequence[Creature], blockers: Sequence[Creature]) -> None:
    """Refuse a full attack enumeration the exact method cannot finish.

    Raises:
        TooManyCombinationsError: If the board is past what will be enumerated.
    """
    _check_dimensions(attackers, blockers)
    _check(resolutions_for(len(attackers), len(blockers)), attackers, blockers)


def _check_dimensions(attackers: Sequence[Creature], blockers: Sequence[Creature]) -> None:
    """The two cheap per-dimension exits, for the sake of a clearer message."""
    if len(attackers) > MAX_ATTACKERS:
        msg = f"cannot evaluate {len(attackers)} attackers exactly (limit {MAX_ATTACKERS})"
        raise TooManyCombinationsError(msg)
    if len(blockers) > MAX_BLOCKERS:
        msg = f"cannot evaluate {len(blockers)} blockers exactly (limit {MAX_BLOCKERS})"
        raise TooManyCombinationsError(msg)


def _check(size: int, attackers: Sequence[Creature], blockers: Sequence[Creature]) -> None:
    """Refuse when the measured work is past the budget."""
    if size > MAX_RESOLUTIONS:
        msg = (
            f"cannot evaluate {len(attackers)} attackers against "
            f"{len(blockers)} blockers exactly ({size} combats to resolve)"
        )
        raise TooManyCombinationsError(msg)
