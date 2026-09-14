"""The ``mtgcoach`` command line.

Parsing only. Every subcommand's behaviour lives in ``commands``, and ``main``
takes its arguments and output stream as parameters so the whole surface can be
exercised without a subprocess.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from mtgcoach.carddata import commands, effectcommands
from mtgcoach.carddata.claudecli import ClaudeCliExtractor
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.carddata.paths import validate_set_code
from mtgcoach.carddata.schema import SchemaError
from mtgcoach.carddata.scryfallapi import HttpPages
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from typing import TextIO

DEFAULT_DB = Path("data/cards.sqlite3")
DEFAULT_DATA_ROOT = Path("data")


def _set_code(value: str) -> SetCode:
    """Validate a set code at parse time, so a typo fails before any I/O."""
    code = SetCode(value.upper())
    try:
        validate_set_code(code)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from exc
    return code


def build_parser() -> argparse.ArgumentParser:
    """Build the argument parser."""
    parser = argparse.ArgumentParser(prog="mtgcoach", description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB, help="Card database.")
    parser.add_argument("--data", type=Path, default=DEFAULT_DATA_ROOT, help="Data directory.")
    top = parser.add_subparsers(dest="group", required=True)

    sets = top.add_parser("sets", help="Import and inspect sets.").add_subparsers(
        dest="action", required=True
    )
    fetch = sets.add_parser("fetch", help="Download a set's printings from Scryfall.")
    fetch.add_argument("set_code", type=_set_code)
    fetch.add_argument(
        "--to",
        dest="destination",
        type=Path,
        default=None,
        help="Where to write them. Defaults to <data>/scryfall/<SET>.json.",
    )
    add = sets.add_parser("add", help="Import a set from a Scryfall export.")
    add.add_argument("set_code", type=_set_code)
    add.add_argument("--from", dest="source", type=Path, required=True)
    sets.add_parser("list", help="List imported sets.")
    audit = sets.add_parser("audit", help="Report what a set would cost to support.")
    audit.add_argument("set_code", type=_set_code)

    decks = top.add_parser("decks", help="Inspect decklists.").add_subparsers(
        dest="action", required=True
    )
    check = decks.add_parser("verify", help="Verify shipped decklists for a set.")
    check.add_argument("set_code", type=_set_code)

    effects = top.add_parser(
        "effects", help="Extract, review and seal card behaviour."
    ).add_subparsers(dest="action", required=True)
    for name, helptext in (
        ("extract", "Propose abilities for a set (calls a model)."),
        ("review", "Show what is waiting to be sealed."),
        ("seal", "Promote reviewed proposals to the engine's fixture."),
        ("check", "Verify a sealed fixture matches its manifest."),
    ):
        sub = effects.add_parser(name, help=helptext)
        sub.add_argument("set_code", type=_set_code)
        if name == "seal":
            sub.add_argument(
                "--accept",
                action="store_true",
                help="Confirm the proposals have been reviewed.",
            )

    pool = top.add_parser("pool", help="Choose what you own.").add_subparsers(
        dest="action", required=True
    )
    pool.add_parser("show", help="Show the current collection.")
    for name, helptext in (("enable", "Add a set."), ("disable", "Remove a set.")):
        sub = pool.add_parser(name, help=helptext)
        sub.add_argument("set_code", type=_set_code)

    return parser


def _destination(args: argparse.Namespace, data_root: Path) -> Path:
    """Where a fetched set goes. Beside the other per-set data by default."""
    chosen: Path | None = args.destination
    return chosen if chosen is not None else data_root / "scryfall" / f"{args.set_code}.json"


def _dispatch(args: argparse.Namespace, store: CardStore, data_root: Path, out: TextIO) -> int:
    """Route a parsed command to its handler.

    A table rather than a match: every pair is listed explicitly, so no command
    can end up in a catch-all arm where a typo in its name would silently run
    the wrong thing. argparse has already rejected any pair not listed here.
    """
    handlers: dict[tuple[str, str], Callable[[], int]] = {
        ("sets", "fetch"): lambda: commands.sets_fetch(
            HttpPages(), args.set_code, _destination(args, data_root), out
        ),
        ("sets", "add"): lambda: commands.sets_add(store, args.source, args.set_code, out),
        ("sets", "list"): lambda: commands.sets_list(store, out),
        ("sets", "audit"): lambda: commands.sets_audit(store, args.set_code, out),
        ("decks", "verify"): lambda: commands.decks_verify(store, data_root, args.set_code, out),
        ("effects", "extract"): lambda: effectcommands.extract(
            store, ClaudeCliExtractor(), data_root, args.set_code, out
        ),
        ("effects", "review"): lambda: effectcommands.review(data_root, args.set_code, out),
        ("effects", "seal"): lambda: effectcommands.seal(
            data_root,
            args.set_code,
            out,
            ClaudeCliExtractor().model,
            accepted=args.accept,
        ),
        ("effects", "check"): lambda: effectcommands.check(data_root, args.set_code, out),
        ("pool", "show"): lambda: commands.pool_show(store, out),
        ("pool", "enable"): lambda: commands.pool_enable(store, args.set_code, out),
        ("pool", "disable"): lambda: commands.pool_disable(store, args.set_code, out),
    }
    return handlers[(args.group, args.action)]()


def main(argv: Sequence[str] | None = None, out: TextIO | None = None) -> int:
    """Run one command. Returns the process exit code.

    Expected failures -- a missing file, a malformed export, a corrupted
    database row -- are reported as a diagnostic and a non-zero code. A
    traceback is the right answer for a bug in this code and the wrong one for
    a typo in a filename, and a user cannot tell the two apart.
    """
    parser = build_parser()
    args = parser.parse_args(argv)
    stream = out if out is not None else sys.stdout
    db_path: Path = args.db
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        with CardStore.open(str(db_path)) as store:
            return _dispatch(args, store, args.data, stream)
    except (OSError, MalformedJsonError, SchemaError, ValueError) as exc:
        print(f"error: {commands.safe(str(exc))}", file=stream)
        return commands.FAILED


if __name__ == "__main__":
    sys.exit(main())
