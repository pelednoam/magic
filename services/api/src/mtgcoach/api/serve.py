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
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import uvicorn

from mtgcoach.api.address import reachable
from mtgcoach.api.app import create_app
from mtgcoach.api.cards import build
from mtgcoach.api.context import Claude
from mtgcoach.api.seating import SEATS
from mtgcoach.api.tokenfile import seating_at
from mtgcoach.carddata.decks import load_set_decks
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode
from mtgcoach.rules.corpus import CorpusError
from mtgcoach.rules.library import Installed, RulesNotInstalledError, installed_at, rules_path

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from fastapi import FastAPI

    from mtgcoach.api.seating import Seating
    from mtgcoach.carddata.decks import Decklist
    from mtgcoach.core.ids import OracleId

DEFAULT_PORT = 8000


#: Where the server's tokens live, relative to the data directory. Beside the
#: card database, because they belong to this installation rather than to a
#: run. A filename, not a secret -- the secrets are what `tokenfile.seating_at`
#: puts in it, one per seat.
TOKEN_PATH = Path("token")


@dataclass(frozen=True, slots=True)
class Serving:
    """A built app and the seating it will ask for.

    Together because the tokens are read from a file and printing them is the
    only way they reach the two devices. Returning them beside the app means
    one read and one place that knows where the file is; the first version read
    it twice and left two call sites able to disagree.
    """

    app: FastAPI
    seating: Seating


def assemble(db: Path, data_root: Path, set_code: SetCode) -> Serving:
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

    decks = {deck.key: library(deck, names) for deck in load_set_decks(data_root, set_code)}
    seating = seating_at(data_root / TOKEN_PATH)
    rules = _rules(data_root)
    asked = Claude(
        rules=rules.index if rules is not None else None,
        rules_revision=rules.revision if rules is not None else "",
    )
    app = create_app(catalogue, decks, seating, asked, data_root)
    return Serving(app=app, seating=seating)


def _rules(data_root: Path) -> Installed | None:
    """The rules index and its revision, or None with a line saying why not.

    Not installing the rules is a legitimate way to run this: the tracker, the
    engine and the turn coach all work without them, and only the question box
    goes away. So a missing document is a printed sentence and a server that
    starts, not a refusal to start -- but it is printed, because a question box
    that silently answers nothing is worse than one that says it is switched
    off.
    """
    try:
        return installed_at(rules_path(data_root))
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


def library(deck: Decklist, names: Mapping[str, OracleId]) -> tuple[str, ...]:
    """One decklist as the oracle ids to deal, in order.

    Public because it makes a rules-visible decision of its own and now has a
    test to itself; see ``tests/api/test_serve_decks.py``. It was private, and
    the only thing exercising the dropped-card branch was the card fixture
    being too small to cover a decklist -- which stopped being true when that
    fixture grew to the whole box.

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

    serving = assemble(args.db, args.data, SetCode(args.set_code))
    _announce(serving.seating, reachable(args.host, args.port))
    uvicorn.run(serving.app, host=args.host, port=args.port)
    return 0


def _announce(seating: Seating, url: str) -> None:
    """Print the address and a token per seat, because nothing else will.

    The tokens are the whole of the server's access control and each device
    needs its own. Printing them at startup is how they get from the laptop to
    the two devices -- there is nobody to email them to. The address is here for
    the same reason: the app defaults to ``localhost``, which on a phone is the
    phone.

    **One token to each device, and not the other.** A token *is* the seat: the
    device that holds the one marked ``them`` is that player, sees that hand
    and may act only for it. Giving both to one device puts the arrangement back
    the way it was before seats existed.
    """
    print(f"Magic Coach on {url}")  # noqa: T201 - a console script
    for seat in SEATS:
        print(f"  token for {seat}: {seating.token(seat)}")  # noqa: T201
    print("  give each device one of them, and paste it in when the app asks.")  # noqa: T201
    print("  whichever seat it holds is the player it plays, and the only")  # noqa: T201
    print("  hand it is shown.")  # noqa: T201
    print(f"  the app needs the address too: EXPO_PUBLIC_COACH_URL={url}")  # noqa: T201
    print(  # noqa: T201
        f"  EXPO_PUBLIC_COACH_TOKEN works for a localhost-only session -- it "
        f"would be the {SEATS[0]!r} one -- but Expo bakes it into the bundle "
        f"Metro serves unauthenticated, so on a LAN set the URL and paste the "
        f"token."
    )


if __name__ == "__main__":
    raise SystemExit(main())
