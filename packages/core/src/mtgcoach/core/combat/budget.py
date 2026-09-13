"""How big a combat the exact search will take on.

``MAX_ATTACKERS`` alone was the wrong guard, and it was wrong in the way that
matters: the attack subsets are 2^A, but the blocking assignments are
(A+1)^B -- the *blockers* are the exponent, and they were unbounded. Eight
attackers against eight blockers is around 11e9 resolutions, which is a hang and
not an answer, and the test that showed the limit was safe passed only because
it used no blockers at all.

So the bound is on the work, not on a dimension. And it is a refusal: a coach
that silently switches to a heuristic on a big board is worse than one that says
it cannot be sure, because the player cannot tell which answer they got.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.model import Creature

#: Beyond this many attackers the subset enumeration alone stops being instant.
#: The Beginner Box never fields this many.
MAX_ATTACKERS: Final = 8

#: Beyond this many blockers the assignment search stops being instant.
MAX_BLOCKERS: Final = 6

#: Roughly how many combats the exact search will resolve before refusing.
#: Reached only by boards well past anything the box can produce; the
#: per-dimension caps above are what a real game runs into first.
MAX_COMBINATIONS: Final = 2_000_000


class TooManyCombinationsError(ValueError):
    """This board is too large for the exact search.

    A ``ValueError`` because it is the same kind of refusal as a creature with
    ``*`` power: the question is well formed, and the honest answer is that a
    confident one would be a guess.
    """


def combinations_for(attackers: int, blockers: int) -> int:
    """How many block assignments the search would enumerate."""
    return int((attackers + 1) ** blockers)


def check_size(attackers: Sequence[Creature], blockers: Sequence[Creature]) -> None:
    """Refuse a board the exact search cannot finish.

    Raises:
        TooManyCombinationsError: If either dimension, or the product of the
            two, is past what the search will enumerate.
    """
    if len(attackers) > MAX_ATTACKERS:
        msg = f"cannot evaluate {len(attackers)} attackers exactly (limit {MAX_ATTACKERS})"
        raise TooManyCombinationsError(msg)
    if len(blockers) > MAX_BLOCKERS:
        msg = f"cannot evaluate {len(blockers)} blockers exactly (limit {MAX_BLOCKERS})"
        raise TooManyCombinationsError(msg)
    size = combinations_for(len(attackers), len(blockers))
    if size > MAX_COMBINATIONS:
        msg = (
            f"cannot evaluate {len(attackers)} attackers against "
            f"{len(blockers)} blockers exactly ({size} block assignments)"
        )
        raise TooManyCombinationsError(msg)
