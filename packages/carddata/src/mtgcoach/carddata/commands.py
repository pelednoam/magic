"""What each CLI subcommand does.

Kept apart from argument parsing so the behaviour can be tested by calling a
function with a store and a stream, rather than by driving a parser.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.carddata.decks import load_set_decks, verify
from mtgcoach.carddata.mechanics import audit
from mtgcoach.carddata.scryfall import read_printings

if TYPE_CHECKING:
    from pathlib import Path
    from typing import TextIO

    from mtgcoach.carddata.store import CardStore
    from mtgcoach.core.ids import SetCode

OK = 0
FAILED = 1


def sets_add(store: CardStore, source: Path, set_code: SetCode, out: TextIO) -> int:
    """Import one set from a Scryfall export, ignoring every other set in it."""
    wanted = [(c, s) for c, s in read_printings(source) if s == set_code]
    if not wanted:
        print(f"no {set_code} cards in {source.name}", file=out)
        return FAILED
    written = store.add(wanted)
    distinct = store.count_in(set_code)
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
    report = audit(set_code, store.cards_in_set(set_code))
    print(f"{set_code}: {report.card_count} cards", file=out)
    if report.card_count == 0:
        print("  nothing imported for this set", file=out)
        return FAILED
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
        print(f"    {keyword} ({count} card{'' if count == 1 else 's'})", file=out)
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
            print(f"  verified  {deck.name:<10} {verdict.total} cards", file=out)
            continue
        failures += 1
        print(f"  PARTIAL   {deck.name:<10} {verdict.total} cards", file=out)
        for reason in verdict.reasons:
            print(f"              {reason}", file=out)
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
