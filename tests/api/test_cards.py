"""Building the catalogue out of the two places a card is described.

The store knows what a card *is*; the sealed fixture knows what it *does*. A
card can be in one and not the other, and this is where that is decided.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from mtgcoach.api.cards import Catalogue, build
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.core.ids import OracleId

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PLAYABLE = FIXTURES / "scryfall_fdn_playable.json"
EFFECTS = Path(__file__).resolve().parents[2] / "data" / "sets" / "FDN" / "effects.json"

FOREST = OracleId("b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6")


def test_a_card_arrives_with_its_facts_and_its_rules() -> None:
    catalogue = build(cards_in(PLAYABLE), EFFECTS)
    facts = catalogue.facts(FOREST)
    assert facts is not None
    assert facts.is_land
    assert catalogue.abilities(FOREST), "the sealed fixture gives Forest a mana ability"


def test_without_a_sealed_fixture_the_cards_still_load() -> None:
    """A set nobody has extracted yet is still a set you can look cards up in."""
    catalogue = build(cards_in(PLAYABLE))
    assert catalogue.facts(FOREST) is not None
    assert catalogue.abilities(FOREST) == ()


def test_a_sealed_fixture_that_is_not_there_is_not_an_error() -> None:
    catalogue = build(cards_in(PLAYABLE), FIXTURES / "no-such-file.json")
    assert catalogue.abilities(FOREST) == ()


def test_a_card_whose_cost_cannot_be_parsed_is_left_out() -> None:
    """One bad card must not take the set with it, and must not be guessed at."""
    cards = list(cards_in(PLAYABLE))
    broken = replace(cards[0], faces=(replace(cards[0].faces[0], mana_cost="{W/P}"),))
    catalogue = build([broken, *cards[1:]])
    assert catalogue.facts(broken.oracle_id) is None
    assert catalogue.facts(cards[1].oracle_id) is not None, "the rest of the set survives"


def test_an_unknown_card_has_no_facts_and_no_rules() -> None:
    catalogue = build(cards_in(PLAYABLE), EFFECTS)
    assert catalogue.facts(OracleId("nope")) is None
    assert catalogue.abilities(OracleId("nope")) == ()


def test_a_name_falls_back_to_the_identifier() -> None:
    """A raw id tells the player something true: the server cannot name it."""
    catalogue = build(cards_in(PLAYABLE), EFFECTS)
    assert catalogue.name(FOREST) == "Forest"
    assert catalogue.name(OracleId("nope")) == "nope"


def test_an_empty_catalogue_is_usable() -> None:
    empty = Catalogue()
    assert empty.facts(FOREST) is None
    assert empty.abilities(FOREST) == ()
