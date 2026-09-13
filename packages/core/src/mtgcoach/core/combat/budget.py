"""How big a combat the exact search will take on.

Two earlier versions of this bound got it wrong, in the same way twice: they
counted a dimension and told a story about it.

``MAX_ATTACKERS`` alone was wrong because the attack subsets are 2^A but the
block assignments are (A+1)^B -- the *blockers* are the exponent. Then bounding
``(A+1)**B`` was wrong because that is the work of a single ``best_defence``,
and ``plans`` runs one per attack subset. At the caps those two stories admitted
eight attackers against six blockers, which takes five minutes.

So the bound is measured, not reasoned about. ``resolutions_for`` counts what
the search actually does -- every block assignment, times every order the
attacker could assign damage in -- and it tracks real time to within a few
percent across every board shape tried. The constant below is that count at
roughly four seconds.

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

#: How many combats the exact search will resolve before refusing. Measured:
#: about 38 microseconds each, so this is a shade under four seconds. It admits
#: six attackers against four blockers, eight against three, or four against
#: four -- past anything the Beginner Box fields, and short of the boards that
#: would make the coach appear to have hung.
MAX_RESOLUTIONS: Final = 100_000


class TooManyCombinationsError(ValueError):
    """This board is too large for the exact search.

    A ``ValueError`` because it is the same kind of refusal as a creature with
    ``*`` power: the question is well formed, and the honest answer is that a
    confident one would be a guess.
    """


def _arrangements(attackers: int, blockers: int) -> int:
    """Every way to block ``attackers``, each group in every damage order.

    Choosing which blockers block, which attacker each one blocks, and the order
    the attacking player assigns damage within a group, is exactly arranging
    some of the blockers into ``attackers`` ordered lists. That is the rising
    factorial, summed over how many blockers are used.
    """
    total = 0
    for used in range(blockers + 1):
        rising = math.prod(attackers + step for step in range(used))
        total += math.comb(blockers, used) * rising
    return total


def resolutions_for(attackers: int, blockers: int) -> int:
    """How many combats ``plans`` would resolve for this board.

    One ``best_defence`` per attack subset, and within each, one ``resolve`` per
    block assignment per damage order.
    """
    return sum(
        math.comb(attackers, size) * _arrangements(size, blockers) for size in range(attackers + 1)
    )


def check_defence_size(attackers: Sequence[Creature], blockers: Sequence[Creature]) -> None:
    """Refuse a single blocking search the exact method cannot finish.

    Raises:
        TooManyCombinationsError: If the board is past what will be enumerated.
    """
    _check_dimensions(attackers, blockers)
    _check(_arrangements(len(attackers), len(blockers)), attackers, blockers)


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
