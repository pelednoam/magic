"""Decklists, and refusing to believe them without evidence."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import pytest

from mtgcoach.carddata.decks import (
    JUMPSTART_DECK_SIZE,
    Completeness,
    DeckEntry,
    Decklist,
    load_set_decks,
    verify,
)
from mtgcoach.core.ids import SetCode

REPO = Path(__file__).resolve().parent.parent.parent
DATA = REPO / "data"
NAMES = frozenset(json.loads((REPO / "tests" / "fixtures" / "fdn_card_names.json").read_text()))
FDN = SetCode("FDN")

BOX_SIZE = 200
DECK_COUNT = 10


def _deck(*entries: tuple[str, int]) -> Decklist:
    return Decklist(
        key="test",
        name="Test",
        color="W",
        tutorial=False,
        sources=(),
        entries=tuple(DeckEntry(n, q) for n, q in entries),
    )


# --- the shipped data -------------------------------------------------------


def test_every_shipped_deck_verifies() -> None:
    """The whole point. A deck that cannot be verified must not ship silently."""
    for deck in load_set_decks(DATA, FDN):
        verdict = verify(deck, NAMES)
        assert verdict.is_verified, f"{deck.key}: {'; '.join(verdict.reasons)}"


def test_the_box_contains_exactly_two_hundred_cards() -> None:
    """An independent check: the product is advertised as 200 cards."""
    decks = load_set_decks(DATA, FDN)
    assert len(decks) == DECK_COUNT
    assert sum(d.total for d in decks) == BOX_SIZE


def test_two_decks_are_marked_as_the_tutorial_pair() -> None:
    tutorial = {d.key for d in load_set_decks(DATA, FDN) if d.tutorial}
    assert tutorial == {"cats", "vampires"}


def test_every_deck_records_where_it_came_from() -> None:
    """Provenance is the difference between data and hearsay."""
    for deck in load_set_decks(DATA, FDN):
        assert deck.sources, f"{deck.key} has no source"


def test_the_colours_cover_each_pair() -> None:
    colors = sorted(d.color for d in load_set_decks(DATA, FDN))
    assert colors == ["B", "B", "G", "G", "R", "R", "U", "U", "W", "W"]


# --- the design: completeness cannot be asserted, only earned ---------------


def test_a_decklist_has_no_field_claiming_it_is_complete() -> None:
    """A stored flag can be wrong in the data file and nobody would notice.

    Completeness is computed by ``verify`` every time it is needed, so there is
    no field for a bad transcription to lie in.
    """
    names = {f.name for f in dataclasses.fields(Decklist)}
    assert not names & {"complete", "completeness", "verified", "is_complete"}


# --- verification ----------------------------------------------------------


def test_a_correct_deck_verifies() -> None:
    deck = _deck(("Plains", 19), ("Savannah Lions", 1))
    verdict = verify(deck, frozenset({"Plains", "Savannah Lions"}))
    assert verdict.completeness is Completeness.VERIFIED
    assert verdict.reasons == ()


@pytest.mark.parametrize("count", [18, 19, 21])
def test_the_wrong_number_of_cards_fails(count: int) -> None:
    verdict = verify(_deck(("Plains", count)), frozenset({"Plains"}))
    assert not verdict.is_verified
    assert f"{count} cards listed, expected 20" in verdict.reasons[0]


def test_a_name_that_is_not_a_card_fails() -> None:
    """The real error this check was written for.

    A transcription of the Goblins deck read "Volley", "Veteran Goblin" and
    "Firebomb". The actual cards are ``Volley Veteran`` and ``Goblin Firebomb``.
    """
    deck = _deck(("Mountain", 17), ("Volley", 1), ("Veteran Goblin", 1), ("Firebomb", 1))
    verdict = verify(deck, NAMES)
    assert not verdict.is_verified
    assert verdict.unknown_names == ("Firebomb", "Veteran Goblin", "Volley")


def test_the_real_names_do_exist() -> None:
    assert "Volley Veteran" in NAMES
    assert "Goblin Firebomb" in NAMES


def test_a_deck_can_fail_both_checks_at_once() -> None:
    deck = _deck(("Plains", 21), ("Nonesuch", 1))
    verdict = verify(deck, frozenset({"Plains"}))
    assert len(verdict.reasons) == 2


def test_the_expected_size_is_a_parameter() -> None:
    """Other products use other deck sizes; the rule is not baked in."""
    deck = _deck(("Plains", 40))
    assert verify(deck, frozenset({"Plains"}), expected=40).is_verified
    assert JUMPSTART_DECK_SIZE == 20
