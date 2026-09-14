"""A season, as something worth reading.

Split from ``cli`` because running games and describing them are different
jobs, and the describing is the one that gets edited: it is written for
somebody deciding what to do next, so it leads with what went wrong and the
seed that reproduces it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.selfplay.records import Reached, Season

#: How many of a season's troubles to print. A defect usually fires in every
#: game, and forty identical lines are harder to read than four.
SHOWN = 8

#: How many unknown cards to name. The whole list is often most of a set.
NAMED = 12


def said(run: Season) -> str:
    """The season, as something worth reading."""
    lines = [
        f"{len(run.games)} games, {run.clean} clean, {len(run.trouble)} problem(s)",
        f"  turns: {_spread(tuple(game.turns for game in run.games))}",
        f"  events applied: {sum(game.events for game in run.games)}",
        f"  endings: {_tally(tuple(game.ending for game in run.games))}",
        # What it *reached*, not just what it found. A clean season is only
        # reassuring in proportion to how much of a game of Magic happened in
        # it, and a harness that cannot say is not evidence.
        _covered(run),
        _reached(run.reached),
    ]
    lines.extend(
        f"  coach: {tally.asked} asked, {tally.trusted} trusted, "
        f"{tally.untrusted} failed checks, {tally.refused} no answer"
        for tally in run.coaching
    )
    lines.extend(
        f"    disagreed: {reason}"
        for reason in dict.fromkeys(
            reason for tally in run.coaching for reason in tally.disagreements
        )
    )
    if run.unknown:
        lines += [
            f"  cards nothing can speak for ({len(run.unknown)}): "
            f"{', '.join(run.unknown[:NAMED])}" + (", ..." if len(run.unknown) > NAMED else ""),
        ]
    for game in run.games:
        for problem in game.trouble[:SHOWN]:
            lines.append(f"  seed {game.seed} {game.decks[0]} v {game.decks[1]} -- {problem}")
    return "\n".join(lines)


def _covered(run: Season) -> str:
    """Which decks and matchups a season actually played."""
    return (
        f"  covered: {len(run.decks)} deck(s), {run.pairings} pairing(s) -- {', '.join(run.decks)}"
    )


def _reached(reached: Reached) -> str:
    """How much of a game of Magic happened."""
    return (
        f"  reached: {reached.lands} land drops, {reached.spells} spells cast, "
        f"{reached.attacks} attacks, {reached.triggers} turns with a trigger, "
        f"biggest board {reached.biggest_board}"
    )


def _spread(numbers: tuple[int, ...]) -> str:
    """Shortest, typical, longest."""
    ordered = sorted(numbers)
    return f"{ordered[0]}-{ordered[-1]}, median {ordered[len(ordered) // 2]}"


def _tally(endings: tuple[str, ...]) -> str:
    """How many games ended each way."""
    seen = {ending: endings.count(ending) for ending in sorted(set(endings))}
    return ", ".join(f"{count} {ending}" for ending, count in seen.items())
