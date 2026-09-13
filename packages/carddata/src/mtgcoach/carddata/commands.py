"""What each CLI subcommand does.

Kept apart from argument parsing so the behaviour can be tested by calling a
function with a store and a stream, rather than by driving a parser.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from mtgcoach.carddata import mechanics
from mtgcoach.carddata.decks import load_set_decks, verify
from mtgcoach.carddata.scryfall import read_printings

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TextIO

    from mtgcoach.carddata.store import CardStore
    from mtgcoach.core.ids import SetCode

OK = 0
FAILED = 1

#: Control characters, escape included. Card names, keywords and deck names all
#: come from files we did not write, and printing an unescaped escape sequence
#: lets a crafted file repaint or clear the terminal it is reported in.
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")

#: How many skipped cards to name before summarising.
_ERRORS_SHOWN = 3


def safe(text: str) -> str:
    """Render untrusted text for a terminal."""
    return _CONTROL.sub("?", text)


def sets_add(store: CardStore, source: Path, set_code: SetCode, out: TextIO) -> int:
    """Import one set from a Scryfall export, ignoring every other set in it.

    A malformed card is skipped and reported rather than aborting the import: a
    bulk file spans every set ever printed, and abandoning a several-hundred-
    megabyte import over one odd card in a set you do not own helps nobody.
    """
    skipped: list[str] = []
    wanted = [
        (c, s)
        for c, s in read_printings(source, on_error=lambda e: skipped.append(str(e)))
        if s == set_code
    ]
    for message in skipped[:_ERRORS_SHOWN]:
        print(f"  skipped: {safe(message)}", file=out)
    if len(skipped) > _ERRORS_SHOWN:
        print(f"  ... and {len(skipped) - _ERRORS_SHOWN} more skipped", file=out)
    if not wanted:
        print(f"no {set_code} cards in {safe(source.name)}", file=out)
        return FAILED
    written = store.add(wanted)
    distinct = len({card.oracle_id for card, _ in wanted})
    # A set file lists printings, not cards: variants and alternate art collapse
    # onto one oracle id. Reporting only the larger number would imply the store
    # holds cards it does not.
    print(
        f"imported {written} {set_code} printings ({distinct} distinct cards) from {source.name}",
        file=out,
    )
    return OK


def sets_list(store: CardStore, out: TextIO) -> int:
    """List the sets held, with card counts."""
    codes = store.set_codes()
    if not codes:
        print("no sets imported yet; try `mtgcoach sets add`", file=out)
        return OK
    owned = store.collection().sets
    for code in codes:
        mark = "owned" if code in owned else "     "
        print(f"  {mark}  {code}  {store.count_in(code):>4} cards", file=out)
    return OK


def sets_audit(store: CardStore, set_code: SetCode, out: TextIO) -> int:
    """Report what a set would cost to coach with."""
    report = mechanics.audit(set_code, store.cards_in_set(set_code), mechanics.SUPPORTED_KEYWORDS)
    print(f"{set_code}: {report.card_count} cards", file=out)
    if report.card_count == 0:
        print("  nothing imported for this set", file=out)
        return FAILED
    if not report.keyword_counts:
        print("  no keyword mechanics at all", file=out)
        return OK
    print(f"  {len(report.keyword_counts)} distinct mechanics", file=out)
    if report.fully_supported:
        print("  every mechanic is modelled", file=out)
        return OK
    print(
        f"  {len(report.unsupported)} not modelled, affecting "
        f"{report.affected_cards} cards ({report.affected_fraction:.0%}):",
        file=out,
    )
    for keyword in report.unsupported:
        count = report.keyword_counts[keyword]
        plural = "" if count == 1 else "s"
        print(f"    {safe(keyword)} ({count} card{plural})", file=out)
    return OK


def decks_verify(store: CardStore, data_root: Path, set_code: SetCode, out: TextIO) -> int:
    """Check every shipped decklist for that set against the stored cards."""
    known = store.names_in(set_code)
    if not known:
        print(f"no {set_code} cards imported; cannot verify names", file=out)
        return FAILED
    decks = load_set_decks(data_root, set_code)
    if not decks:
        print(f"no decklists shipped for {set_code}", file=out)
        return FAILED

    failures = 0
    for deck in decks:
        verdict = verify(deck, known)
        if verdict.is_verified:
            print(f"  verified  {safe(deck.name):<10} {verdict.total} cards", file=out)
            continue
        failures += 1
        print(f"  PARTIAL   {safe(deck.name):<10} {verdict.total} cards", file=out)
        for reason in verdict.reasons:
            print(f"              {safe(reason)}", file=out)
    print(f"{len(decks) - failures}/{len(decks)} decklists verified", file=out)
    return FAILED if failures else OK


def pool_show(store: CardStore, out: TextIO) -> int:
    """Show which sets recognition and deck building are scoped to."""
    collection = store.collection()
    if collection.is_empty:
        print("nothing owned yet; try `mtgcoach pool enable FDN`", file=out)
        return OK
    total = len(store.cards_in(collection))
    for code in sorted(collection.sets):
        print(f"  {code}", file=out)
    for oracle_id in sorted(collection.extra_cards):
        print(f"  single {oracle_id}", file=out)
    print(f"{total} cards in scope", file=out)
    return OK


def pool_enable(store: CardStore, set_code: SetCode, out: TextIO) -> int:
    """Add a set to the collection."""
    if set_code not in store.set_codes():
        print(f"{set_code} is not imported; run `mtgcoach sets add` first", file=out)
        return FAILED
    store.enable_set(set_code)
    print(f"{set_code} is now in scope", file=out)
    return OK


def pool_disable(store: CardStore, set_code: SetCode, out: TextIO) -> int:
    """Remove a set from the collection, keeping its card data."""
    store.disable_set(set_code)
    print(f"{set_code} is no longer in scope", file=out)
    return OK
