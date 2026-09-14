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
from mtgcoach.selfplay.journal import Journal, read
from mtgcoach.selfplay.moves import Seat
from mtgcoach.selfplay.policy import Greedy
from mtgcoach.selfplay.records import Game, Season
from mtgcoach.selfplay.replaying import Replayed
from mtgcoach.selfplay.saying import said

if TYPE_CHECKING:
    from collections.abc import Sequence

#: The set the Beginner Box is, and the only one imported so far.
DEFAULT_SET: Final = SetCode("FDN")

#: An agent that keeps a tally: the coach, or a replay of one.
type Scored = Coached | Replayed

#: A game needs two decks that can be dealt whole.
PLAYERS: Final = 2


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
    #: Where to write every decision, so the season can be run again. A
    #: coached season without one cannot be: the coach is a language model,
    #: and a seed does not reproduce it.
    journal: Path | None = None
    #: A journal to play back instead of asking. See ``replaying``.
    replay: Path | None = None


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
    tallies: list[Scored] = []
    for number in range(games):
        this = seed + number
        chosen = pairs[number % len(pairs)]
        seats = tuple(
            Seat(seat, deck, _agent(run, this, offset, tallies))
            for offset, (seat, deck) in enumerate(
                ((dealing.YOU, chosen[0]), (dealing.THEM, chosen[1]))
            )
        )
        state = dealing.dealt(decks, chosen, this)
        played.append(playing.play((seats[0], seats[1]), state, catalogue, this))
    return Season(games=tuple(played), coaching=tuple(agent.tally for agent in tallies))


def _agent(run: Run, seed: int, offset: int, kept: list[Scored]) -> Greedy | Scored:
    """One seat's agent, and a handle on its tally if it keeps one.

    The two coached kinds share a seed with the game rather than with the
    seat, because a journal is keyed by the game -- the seat is in the key
    separately.
    """
    if run.replay is not None:
        playing_back = Replayed(answers=read(run.replay), seed=seed)
        kept.append(playing_back)
        return playing_back
    if not run.coach:
        return Greedy(seed=seed + offset)
    asking = Coached(
        explainer=ClaudeCliExplainer(Cli()),
        seed=seed,
        journal=Journal(run.journal) if run.journal is not None else None,
    )
    kept.append(asking)
    return asking


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
    parser.add_argument(
        "--journal",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "write every coach decision here, one JSON line each, so the "
            "season can be run again with --replay. A coached season without "
            "one cannot be repeated: a seed reproduces the deal, not the model"
        ),
    )
    parser.add_argument(
        "--replay",
        type=Path,
        default=None,
        metavar="FILE",
        help=(
            "play a journal back instead of asking. The identical game in a "
            "second, as many times as you like -- and against a changed "
            "engine, which is how you learn whether the change moved it"
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
            journal=args.journal,
            replay=args.replay,
        )
    )
    print(said(run))  # noqa: T201 - a console script
    return 1 if run.trouble else 0


if __name__ == "__main__":
    sys.exit(main())
