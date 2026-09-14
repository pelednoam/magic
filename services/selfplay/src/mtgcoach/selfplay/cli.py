"""Run a season of games and say what happened.

    uv run python -m mtgcoach.selfplay --games 200

The output is written for somebody deciding what to do next, so it leads with
what went wrong and how to reproduce it. A clean run is one line; a run that
found something prints the seed, because a seed is a whole game replayed
exactly.
"""

from __future__ import annotations

import argparse
import itertools
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final

from mtgcoach.api.cards import build
from mtgcoach.api.claude import Cli
from mtgcoach.api.explainer import ClaudeCliExplainer
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode
from mtgcoach.selfplay import dealing, playing
from mtgcoach.selfplay.coached import Coached
from mtgcoach.selfplay.moves import Seat
from mtgcoach.selfplay.policy import Greedy
from mtgcoach.selfplay.records import Game, Season

if TYPE_CHECKING:
    from collections.abc import Sequence

#: The set the Beginner Box is, and the only one imported so far.
DEFAULT_SET: Final = SetCode("FDN")

#: How many of a season's troubles to print. A defect usually fires in every
#: game, and forty identical lines are harder to read than four.
SHOWN = 8

#: A game needs two decks that can be dealt whole.
PLAYERS: Final = 2

#: How many unknown cards to name. The whole list is often most of a set.
NAMED = 12


@dataclass(frozen=True, slots=True)
class Run:
    """What to play.

    One object because ``season`` is otherwise seven arguments, six of which
    are paths and names that always travel together.
    """

    db: Path = Path("data/cards.sqlite3")
    data_root: Path = Path("data")
    set_code: SetCode = DEFAULT_SET
    games: int = 50
    seed: int = 0
    #: Whether the coach plays. One subprocess per decision, so a game is
    #: minutes rather than milliseconds -- see ``coached``.
    coach: bool = False


def season(run: Run) -> Season:
    """Play ``run.games`` games, pairing every deck against another.

    Raises:
        ValueError: If the set has no cards imported.
    """
    db, data_root, set_code = run.db, run.data_root, run.set_code
    games, seed = run.games, run.seed
    with CardStore.open(str(db)) as store:
        cards = store.cards_in_set(set_code)
        if not cards:
            msg = f"no {set_code} cards in {db}; run `mtgcoach sets add {set_code}` first"
            raise ValueError(msg)
        catalogue = build(cards, effects_path(data_root, set_code))
        names = {card.name: card.oracle_id for card in cards}

    decks = dealing.table(data_root, set_code, names)
    if len(decks) < PLAYERS:
        msg = (
            f"only {len(decks)} {set_code} deck(s) can be dealt from {db}; "
            f"the import does not cover them. Run `mtgcoach sets add {set_code}`."
        )
        raise ValueError(msg)
    pairs = list(itertools.permutations(sorted(decks), 2))
    played: list[Game] = []
    tallies: list[Coached] = []
    for number in range(games):
        this = seed + number
        chosen = pairs[number % len(pairs)]
        seats = tuple(
            Seat(seat, deck, _agent(this + offset, coach=run.coach, kept=tallies))
            for offset, (seat, deck) in enumerate(
                ((dealing.YOU, chosen[0]), (dealing.THEM, chosen[1]))
            )
        )
        state = dealing.dealt(decks, chosen, this)
        played.append(playing.play((seats[0], seats[1]), state, catalogue, this))
    return Season(games=tuple(played), coaching=tuple(agent.tally for agent in tallies))


def _agent(seed: int, *, coach: bool, kept: list[Coached]) -> Greedy | Coached:
    """One seat's agent, and a handle on its tally if it keeps one."""
    if not coach:
        return Greedy(seed=seed)
    asking = Coached(explainer=ClaudeCliExplainer(Cli()))
    kept.append(asking)
    return asking


def said(run: Season) -> str:
    """The season, as something worth reading."""
    lines = [
        f"{len(run.games)} games, {run.clean} clean, {len(run.trouble)} problem(s)",
        f"  turns: {_spread(tuple(game.turns for game in run.games))}",
        f"  events applied: {sum(game.events for game in run.games)}",
        f"  endings: {_tally(tuple(game.ending for game in run.games))}",
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


def _spread(numbers: tuple[int, ...]) -> str:
    """Shortest, typical, longest."""
    ordered = sorted(numbers)
    return f"{ordered[0]}-{ordered[-1]}, median {ordered[len(ordered) // 2]}"


def _tally(endings: tuple[str, ...]) -> str:
    """How many games ended each way."""
    seen = {ending: endings.count(ending) for ending in sorted(set(endings))}
    return ", ".join(f"{count} {ending}" for ending, count in seen.items())


def main(argv: Sequence[str] | None = None) -> int:
    """Play a season and print it."""
    parser = argparse.ArgumentParser(description="Play games against itself, and watch.")
    parser.add_argument("--db", type=Path, default=Path("data/cards.sqlite3"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--set", dest="set_code", default=DEFAULT_SET)
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument(
        "--coach",
        action="store_true",
        help=(
            "let Claude play both seats. One subprocess per decision, so use "
            "--games 1 and expect minutes"
        ),
    )
    args = parser.parse_args(argv)

    run = season(
        Run(
            db=args.db,
            data_root=args.data,
            set_code=SetCode(args.set_code),
            games=args.games,
            seed=args.seed,
            coach=args.coach,
        )
    )
    print(said(run))  # noqa: T201 - a console script
    return 1 if run.trouble else 0


if __name__ == "__main__":
    sys.exit(main())
