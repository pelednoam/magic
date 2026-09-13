"""Resolving one combat: who dies, what gets through, what it costs.

Damage happens in up to two steps. Creatures with first or double strike deal
theirs first (CR 510.5), and anything that dies then never deals its own -- which
is the single most common surprise for a new player, and the reason first strike
is worth more than its stats suggest.

Within a step all damage is simultaneous, so a creature that will die still
deals its damage. That too is unintuitive and worth getting right: trading is a
real play, not an accident.

Three things the *gap between* the steps decides, each of which was wrong here
until a reviewer built the board that showed it:

- a defender reduced to zero life by first strike has lost. State-based actions
  are checked before the regular step (CR 704.3), so nothing that happens in it
  -- a lifelink blocker's damage, say -- can give the life back.
- a creature that was blocked stays blocked (CR 509.1h). If every blocker dies
  to first strike, the attacker does not suddenly connect with the player; it
  assigns its damage to nothing. Getting this wrong made a double striker
  unblockable.
- a blocker whose attacker died in the first step has nothing left to damage,
  and deals none. A double-striking lifelink blocker was gaining life twice for
  hitting a creature that was no longer there.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.combat.board import Board, Hit, Outcome, Side
from mtgcoach.core.combat.model import check_stats

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.combat.model import Blocks, Creature


def _attacker_hits(
    attacker: Creature, blockers: Sequence[Creature], board: Board
) -> tuple[list[Hit], int]:
    """How an attacker splits its damage among its blockers, and what spills.

    ``blockers`` is the living ones in the order the attacking player chose, and
    each is assigned lethal damage before the next gets any (CR 510.1c).
    Assigning the whole power to the first blocker instead meant a 4/4 blocked
    by two 1/1s killed exactly one of them.

    "Lethal" counts damage already marked, and counts a deathtouch hit as lethal
    however small it was (CR 702.2b). Without that a double-striking deathtouch
    trampler spent a second point on a blocker it had already killed in the
    first step, and one point of trample damage vanished.

    A blocked attacker with no living blockers left assigns its damage to
    nothing: the second return value is what reaches the *player*, and only
    trample or being unblocked can put anything there.
    """
    hits: list[Hit] = []
    remaining = attacker.damage
    deathtouch = attacker.has("Deathtouch")
    for blocker in blockers:
        if remaining <= 0:
            break
        needed = (
            0 if board.has_lethal(blocker) else _lethal_for(blocker, board, deathtouch=deathtouch)
        )
        assigned = min(remaining, needed)
        if assigned > 0:
            hits.append(Hit(blocker.instance_id, assigned, deathtouch=deathtouch))
            remaining -= assigned
    if remaining > 0 and not attacker.has("Trample") and blockers:
        # Nowhere else for it to go, and it has to go somewhere: an attacker
        # without trample assigns all its damage among its blockers, whether or
        # not any of it matters. Piling it on is free, and a lifelinker gains
        # the life for it -- which it did not when every blocker already had
        # lethal marked and so took no assignment at all, leaving the damage to
        # vanish along with the life.
        target = hits[-1] if hits else Hit(blockers[0].instance_id, 0, deathtouch=deathtouch)
        merged = Hit(target.target, target.amount + remaining, deathtouch=target.deathtouch)
        if hits:
            hits[-1] = merged
        else:
            hits.append(merged)
        remaining = 0
    # CR 702.19b: only trample lets the excess through to the player.
    return hits, remaining if attacker.has("Trample") else 0


def _lethal_for(blocker: Creature, board: Board, *, deathtouch: bool) -> int:
    """How much more damage counts as lethal to this blocker."""
    if deathtouch:
        return 1
    return max(blocker.toughness - board.marked.get(blocker.instance_id, 0), 0)


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
            own, spilled = [], attacker.damage
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
        if board.is_dead(attacker):
            # Nothing left to assign damage to. A blocker does not turn on the
            # player, and does not go on gaining its controller life.
            continue
        for blocker in blocks.on(attacker):
            if not _deals(blocker, first=first) or board.is_dead(blocker):
                continue
            hits.append(
                Hit(attacker.instance_id, blocker.damage, deathtouch=blocker.has("Deathtouch"))
            )
            if blocker.has("Lifelink"):
                lifelink += blocker.damage
    return Side(tuple(hits), lifelink)


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


def _deals(creature: Creature, *, first: bool) -> bool:
    """Whether this creature deals damage in this step."""
    return creature.deals_first_strike_damage if first else creature.deals_regular_damage


def resolve(attackers: Sequence[Creature], blocks: Blocks, defender_life: int) -> Outcome:
    """Work out what an attack would do, if it were made and blocked this way.

    ``defender_life`` is needed, not merely useful: if first strike takes the
    defender to zero the game is over before the regular step (CR 704.3), and
    without knowing the life total this went on to resolve a step that could
    hand the life back.

    Raises:
        ValueError: If a creature has no fixed power or toughness, or two of
            them share an identity. This is public, so it asks: ``check_stats``
            said every entry point had to, and this one was not doing it.
    """
    check_stats(attackers, blocks.blockers)
    board = Board()
    for first in (True, False):
        _step_damage(attackers, blocks, board, first=first)
        if board.defender_is_dead(defender_life):
            break
    return Outcome(
        damage_to_defender=board.to_defender,
        attackers_lost=_dead(attackers, board),
        blockers_lost=_dead(blocks.blockers, board),
        attacker_life_gained=board.attacker_lifelink,
        defender_life_gained=board.defender_lifelink,
    )


def _dead(creatures: Sequence[Creature], board: Board) -> tuple[Creature, ...]:
    """Those of ``creatures`` that took lethal damage, in a stable order."""
    return tuple(sorted((c for c in creatures if board.is_dead(c)), key=lambda c: c.instance_id))
