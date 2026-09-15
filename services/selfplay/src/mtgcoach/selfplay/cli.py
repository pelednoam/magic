"""Run a season of games and say what happened.

    uv run python -m mtgcoach.selfplay --games 200

The output is written for somebody deciding what to do next, so it leads with
what went wrong and how to reproduce it. A clean run is one line; a run that
found something prints the seed, because a seed is a whole game replayed
exactly.

Argparse and nothing else. What a season *is* lives in ``running``.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mtgcoach.core.ids import SetCode
from mtgcoach.selfplay.running import DEFAULT_SET, Run, season
from mtgcoach.selfplay.saying import said

if TYPE_CHECKING:
    from collections.abc import Sequence


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
