"""Resolving one combat: who dies, what gets through, what it costs.

Damage happens in up to two steps. Creatures with first or double strike deal
theirs first (CR 510.5), and anything that dies then never deals its own -- which
is the single most common surprise for a new player, and the reason first strike
is worth more than its stats suggest.

Within a step all damage is simultaneous, so a creature that will die still
deals its damage. That too is unintuitive and worth getting right: trading is a
real play, not an accident.

A creature that was blocked stays blocked (CR 509.1h). If every blocker dies to
first strike, the attacker does not suddenly connect with the player in the
regular step -- it assigns its damage to nothing at all. Getting this wrong
turned a double striker into an unblockable one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.combat.board import Board, Hit, Outcome, Side

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.model import Blocks, Creature


def _attacker_hits(
    attacker: Creature, blockers: Sequence[Creature], board: Board
) -> tuple[list[Hit], int]:
    """How an attacker splits its damage among its blockers, and what spills.

    ``blockers`` is the living ones, in the order the attacking player chose
    (CR 509.2). Each is assigned lethal damage before the next gets any
    (CR 510.1a) -- assigning the whole power to the first blocker instead meant
    a 4/4 blocked by two 1/1s killed exactly one of them.

    A blocked attacker with no living blockers left assigns its damage to
    nothing: the second return value is what reaches the *player*, and only
    trample or being unblocked can put anything there.
    """
    hits: list[Hit] = []
    remaining = attacker.power
    deathtouch = attacker.has("Deathtouch")
    for blocker in blockers:
        if remaining <= 0:
            break
        # Deathtouch makes one point lethal, so the rest may go elsewhere.
        already = board.marked.get(blocker.instance_id, 0)
        needed = 1 if deathtouch else max(blocker.toughness - already, 0)
        assigned = min(remaining, needed)
        hits.append(Hit(blocker.instance_id, assigned, deathtouch=deathtouch))
        remaining -= assigned
    if remaining > 0 and not attacker.has("Trample") and hits:
        # Nowhere else for it to go, and piling it on is what a player does --
        # it costs nothing and a lifelinker gains the life for it.
        last = hits[-1]
        hits[-1] = Hit(last.target, last.amount + remaining, deathtouch=last.deathtouch)
        remaining = 0
    # CR 702.19b: only trample lets the excess through to the player.
    return hits, remaining if attacker.has("Trample") else 0


def _step_damage(
    attackers: Sequence[Creature], blocks: Blocks, board: Board, *, first: bool
) -> None:
    """Deal one damage step's damage, all of it at once.

    Gathered before any of it lands, because damage within a step is
    simultaneous (CR 510.2): a creature that will die still deals its own.

    The two directions are collected independently. Nesting the blockers' damage
    inside the attackers' loop meant that when a first-striker skipped the
    regular step, so did everything blocking it -- a 2/2 first striker walked
    away from a 5/5.
    """
    offence = _offence(attackers, blocks, board, first=first)
    defence = _defence(attackers, blocks, board, first=first)

    everyone = {c.instance_id: c for c in (*attackers, *blocks.blockers)}
    for hit in (*offence.hits, *defence.hits):
        board.hit(everyone[hit.target], hit.amount, deathtouch=hit.deathtouch)
    board.to_defender += offence.to_defender
    board.attacker_lifelink += offence.lifelink
    board.defender_lifelink += defence.lifelink


def _offence(attackers: Sequence[Creature], blocks: Blocks, board: Board, *, first: bool) -> Side:
    """What the attackers deal this step, and what reaches the player."""
    hits: list[Hit] = []
    to_defender = 0
    lifelink = 0
    for attacker in attackers:
        if not _deals(attacker, first=first) or board.is_dead(attacker):
            continue
        if blocks.on(attacker):
            living = [b for b in blocks.on(attacker) if not board.is_dead(b)]
            own, spilled = _attacker_hits(attacker, living, board)
        else:
            own, spilled = [], attacker.power
        hits.extend(own)
        to_defender += spilled
        if attacker.has("Lifelink"):
            lifelink += sum(h.amount for h in own) + spilled
    return Side(tuple(hits), lifelink, to_defender)


def _defence(attackers: Sequence[Creature], blocks: Blocks, board: Board, *, first: bool) -> Side:
    """What the blockers deal back this step."""
    hits: list[Hit] = []
    lifelink = 0
    for attacker in attackers:
        for blocker in blocks.on(attacker):
            if not _deals(blocker, first=first) or board.is_dead(blocker):
                continue
            hits.append(
                Hit(attacker.instance_id, blocker.power, deathtouch=blocker.has("Deathtouch"))
            )
            if blocker.has("Lifelink"):
                lifelink += blocker.power
    return Side(tuple(hits), lifelink)


def _deals(creature: Creature, *, first: bool) -> bool:
    """Whether this creature deals damage in this step."""
    return creature.deals_first_strike_damage if first else creature.deals_regular_damage


def resolve(attackers: Sequence[Creature], blocks: Blocks) -> Outcome:
    """Work out what an attack would do, if it were made and blocked this way."""
    board = Board()
    for first in (True, False):
        _step_damage(attackers, blocks, board, first=first)
    return Outcome(
        damage_to_defender=board.to_defender,
        attackers_lost=tuple(sorted(a.name for a in attackers if board.is_dead(a))),
        blockers_lost=tuple(sorted(b.name for b in blocks.blockers if board.is_dead(b))),
        attacker_life_gained=board.attacker_lifelink,
        defender_life_gained=board.defender_lifelink,
    )
