"""Starting the server for a real game.

The one place that reads from disk. Everything else takes what it needs as an
argument, which is what lets the tests build a three-card set in memory; this
assembles the real thing out of the store and the sealed fixtures, and is the
only module that knows where either lives.

Run it on the laptop in the same room (§4):

    uv run python -m mtgcoach.api.serve --db data/cards.sqlite3 --set FDN
"""

from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from mtgcoach.api.access import token_at
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import build
from mtgcoach.api.context import Claude
from mtgcoach.carddata.decks import load_set_decks
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode
from mtgcoach.rules.corpus import CorpusError
from mtgcoach.rules.library import RulesNotInstalledError, index_at, rules_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fastapi import FastAPI

    from mtgcoach.carddata.decks import Decklist
    from mtgcoach.core.ids import OracleId
    from mtgcoach.rules.search import RuleIndex

DEFAULT_PORT = 8000


#: Where the server's token lives, relative to the data directory. Beside the
#: card database, because it belongs to this installation rather than to a run.
#: A filename, not a secret -- the secret is what `access.token_at` puts in it.
TOKEN_PATH = Path("token")


def assemble(db: Path, data_root: Path, set_code: SetCode) -> FastAPI:
    """Build the app from the card database and a set's sealed data.

    Raises:
        ValueError: If the set has not been imported. Starting a coach with no
            cards in it would leave every answer "I cannot speak for this", which
            looks like a broken engine rather than an empty database.
    """
    with CardStore.open(str(db)) as store:
        cards = store.cards_in_set(set_code)
        if not cards:
            msg = f"no {set_code} cards in {db}; run `mtgcoach sets add {set_code}` first"
            raise ValueError(msg)
        catalogue = build(cards, effects_path(data_root, set_code))
        names = {card.name: card.oracle_id for card in cards}

    decks = {deck.key: _library(deck, names) for deck in load_set_decks(data_root, set_code)}
    token = token_at(data_root / TOKEN_PATH)
    return create_app(catalogue, decks, token, Claude(rules=_rules(data_root)))


def _rules(data_root: Path) -> RuleIndex | None:
    """The Comprehensive Rules index, or None with a line saying why not.

    Not installing the rules is a legitimate way to run this: the tracker, the
    engine and the turn coach all work without them, and only the question box
    goes away. So a missing document is a printed sentence and a server that
    starts, not a refusal to start -- but it is printed, because a question box
    that silently answers nothing is worse than one that says it is switched
    off.
    """
    try:
        return index_at(rules_path(data_root))
    except RulesNotInstalledError as missing:
        print(f"rules questions are off: {missing}")  # noqa: T201 - this is a console script
        return None
    except (CorpusError, OSError, UnicodeDecodeError, sqlite3.Error) as unreadable:
        # A file that is there but is not the rules: a truncated download, the
        # HTML of an error page, a PDF. Or a Python built without FTS5, which
        # is rare and is still not a reason the tracker cannot start. Catching
        # only "not installed" turned any of these into a stack trace at
        # startup -- over a feature the tracker does not need.
        print(f"rules questions are off: {unreadable}")  # noqa: T201 - console script
        return None


def _library(deck: Decklist, names: Mapping[str, OracleId]) -> tuple[str, ...]:
    """One decklist as the oracle ids to deal, in order.

    A card the store does not have is dropped rather than dealt as a blank. The
    decklists are verified against the store by `mtgcoach decks verify`, so this
    only happens on a partial import -- where a slightly short deck is far more
    useful than a refusal.
    """
    found: list[str] = []
    for entry in deck.entries:
        oracle_id = names.get(entry.name)
        if oracle_id is not None:
            found.extend([str(oracle_id)] * entry.quantity)
    return tuple(found)


def main(argv: Sequence[str] | None = None) -> int:
    """Parse the arguments and serve until stopped."""
    parser = argparse.ArgumentParser(description="Serve the Magic Coach API.")
    parser.add_argument("--db", type=Path, default=Path("data/cards.sqlite3"))
    parser.add_argument("--data", type=Path, default=Path("data"))
    parser.add_argument("--set", dest="set_code", default="FDN")
    parser.add_argument("--host", default="0.0.0.0")  # noqa: S104 - the point is the LAN
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    args = parser.parse_args(argv)

    app = assemble(args.db, args.data, SetCode(args.set_code))
    _announce(args.data, args.host, args.port)
    uvicorn.run(app, host=args.host, port=args.port)
    return 0


def _announce(data_root: Path, host: str, port: int) -> None:
    """Print the address and the token, because nothing else will.

    The token is the whole of the server's access control and the app needs it.
    Printing it at startup is how it gets from the laptop to the phone -- there
    is nobody to email it to.
    """
    where = "localhost" if host in {"0.0.0.0", "::"} else host  # noqa: S104 - the LAN is the point
    token = token_at(data_root / TOKEN_PATH)
    print(f"Magic Coach on http://{where}:{port}")  # noqa: T201 - a console script
    print(f"  token: {token}")  # noqa: T201
    print(  # noqa: T201
        "  give it to the app as EXPO_PUBLIC_COACH_TOKEN, or paste it in when asked"
    )


if __name__ == "__main__":
    raise SystemExit(main())
