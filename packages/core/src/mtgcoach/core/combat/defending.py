"""How well the defender can block, which is what makes an attack worth making.

Split from ``search`` at the line limit, and the seam is the one the search
itself has: enumerate the attacks, and for each ask *this* what the defender
would do about it. The assumption is that they block well, which is the honest
thing to show a beginner -- an attack that only works if the opponent misplays
is not a good attack, it is a gamble.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.combat.assignments import block_assignments, damage_orders, identity
from mtgcoach.core.combat.budget import check_defence_size
from mtgcoach.core.combat.damage import resolve
from mtgcoach.core.combat.model import Blocks, check_stats

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.board import Outcome
    from mtgcoach.core.combat.model import Creature

#: A total order over the creatures an outcome involves, so that a tie is never
#: broken by list position.
type _Identity = tuple[tuple[str, ...], tuple[str, ...]]

#: How the *attacker's* damage assignment is ranked, for a fixed set of blocks.
type _Key = tuple[int, int, int, int, int, _Identity]

#: How a candidate block is ranked. Seven terms; see ``best_defence``.
type _Defence = tuple[int, int, int, int, int, int, _Identity]


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
        outcome = resolve(attackers, order, defender_life)
        key = (
            0 if outcome.defender_life_after(defender_life) <= 0 else 1,
            len(outcome.attackers_lost) - len(outcome.blockers_lost),
            outcome.defender_life_after(defender_life),
            -outcome.attacker_life_gained,
            -sum(c.power + c.toughness for c in outcome.blockers_lost),
            identity(outcome),
        )
        if best_key is None or key < best_key:
            best, best_key = outcome, key
    return best if best is not None else resolve(attackers, blocks, defender_life)


def best_defence(
    attackers: Sequence[Creature], blockers: Sequence[Creature], defender_life: int
) -> Outcome:
    """The outcome when the defender blocks as well as they can.

    In order: do not die; do not lose creatures for nothing; end on as much life
    as possible; let the attacker gain as little as possible. The second has to
    outrank the third or the defender chump-blocks every attack at twenty life,
    which would make the coach far too timid -- an attack that only *looks* bad
    because the model assumed a panicked opponent is exactly the advice a
    beginner cannot afford.

    The third term is the life *total*, not the damage. They differ by lifelink,
    and ranking on damage alone left two blocks that differed only in a
    lifelinker exactly tied -- so the defender declined a free point of life
    whenever the caller happened to list the other blocker first.

    Damage then breaks what the life total cannot. Trample plus lifelink makes
    "take one and gain one" land on the same life as "take none", and that tied
    every remaining term including ``identity``, because both blocks kill the
    same attacker -- so the same board was coached two ways depending on the
    order of the list. Letting nothing through wins: equal on life, and
    strictly safer, since a later effect can remove the lifelink and cannot
    remove damage that was never dealt.

    Creature quality is weighed only as power plus toughness, and only as the
    last tiebreak: trading a 5/5 for a 1/1 with deathtouch still counts as an
    even swap on the terms above it. That is why a ``Plan`` carries the whole
    ``Outcome`` and not just its score.

    Raises:
        ValueError: If a creature has no fixed power or toughness, or this board
            is too large to search exactly.
    """
    check_stats(attackers, blockers)
    check_defence_size(attackers, blockers)
    best: Outcome | None = None
    best_key: _Defence | None = None
    for blocks in block_assignments(attackers, blockers):
        outcome = _best_for_attacker(attackers, blocks, defender_life)
        key = (
            1 if outcome.defender_life_after(defender_life) <= 0 else 0,
            len(outcome.blockers_lost) - len(outcome.attackers_lost),
            -outcome.defender_life_after(defender_life),
            outcome.attacker_life_gained,
            sum(c.power + c.toughness for c in outcome.blockers_lost),
            # Less damage through, when the life *total* ties anyway. Lifelink
            # makes that reachable: blocking with a 1/4 lifelinker takes one
            # trample damage and gains one back, which lands on the same life
            # as blocking with a first-striker and taking none -- and every
            # term above this tied, `identity` included, because both blocks
            # kill the same creature. Hypothesis found it in 120 examples.
            #
            # Prefer the block that lets nothing through. Equal on life and
            # strictly safer: a later effect can take the lifelink away and
            # cannot take away damage that was never dealt.
            outcome.damage_to_defender,
            identity(outcome),
        )
        if best_key is None or key < best_key:
            best, best_key = outcome, key
    return best if best is not None else resolve(attackers, Blocks(), defender_life)
