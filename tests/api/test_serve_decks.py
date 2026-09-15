"""Turning a decklist into the cards a game is dealt from.

Split from ``test_serve`` at the line limit; that file is about starting a
server, this is about the one decision it makes on the way -- what to do with a
decklist entry the card store has never heard of.
"""

from __future__ import annotations

from mtgcoach.api.serve import library
from mtgcoach.carddata.decks import DeckEntry, Decklist
from mtgcoach.core.ids import OracleId


def test_a_card_a_partial_import_lacks_is_dropped_from_the_deck() -> None:
    """A slightly short deck beats a refusal, and it used to be untested.

    This branch was covered only by accident: the card fixture held seven
    cards, so almost every decklist entry was missing and the path ran on every
    test that dealt a deck. Growing the fixture to the whole box -- which is
    what let the self-play season tests run in CI at all -- meant nothing was
    missing any more, and the branch went uncovered.

    So it is tested on purpose now. `mtgcoach decks verify FDN` is what checks
    a decklist against the store; this is the behaviour when somebody has not
    run it.
    """
    deck = Decklist(
        key="partial",
        name="Partial",
        color="G",
        tutorial=False,
        sources=(),
        entries=(DeckEntry("Forest", 2), DeckEntry("Nonesuch", 3)),
    )
    known = {"Forest": OracleId("forest-id")}
    assert library(deck, known) == ("forest-id", "forest-id")
