"""Building the catalogue out of the two places a card is described.

The store knows what a card *is*; the sealed fixture knows what it *does*. A
card can be in one and not the other, and this is where that is decided.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from helpers import UNKNOWN_ABILITY
from mtgcoach.api.cards import Catalogue, build
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.core.ids import OracleId

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
#: How many cards the Beginner Box has, and how many of them the sealed
#: fixture understands all the way down. Written out so a re-seal that changes
#: either number has to say so here.
BOX = 124
MODELLED = 65

PLAYABLE = FIXTURES / "scryfall_fdn_playable.json"

#: Eight unedited Scryfall objects, including the transform and adventure cards
#: whose text lives only on their faces. See ``carddata.test_scryfall``.
SAMPLE = FIXTURES / "scryfall_fdn_sample.json"
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


def test_a_card_the_fixture_cannot_express_is_not_modelled() -> None:
    """Identified, and not understood -- which is most of the box.

    This used to assert the opposite: that no card in the fixture was in that
    state, because the fixture held seven cards chosen to avoid it. That made
    the assertion about the *choice of fixture* rather than about ``modelled``,
    and it also meant the fixture could not deal a single one of the box's ten
    decks -- so three self-play tests failed on every CI run while passing on
    any machine with the real import. Nobody looked, because the workflow was
    red for other reasons too; see ``tools/check_ci_covers_gate.py``.

    The fixture is the whole box now, so the split it documents can be
    asserted: 65 cards understood all the way down, 59 identified and not.
    """
    catalogue = build(cards_in(PLAYABLE), EFFECTS)
    unexpressible = [
        oracle_id
        for oracle_id in catalogue.cards
        if not catalogue.modelled(OracleId(oracle_id)) and catalogue.abilities(OracleId(oracle_id))
    ]
    assert catalogue.modelled(FOREST), "a land with a mana ability is understood"
    assert unexpressible, "the flag distinguishes nothing if every card passes it"
    assert len(catalogue.cards) == BOX
    assert len(catalogue.cards) - len(unexpressible) == MODELLED


def test_a_card_absent_from_the_fixture_is_not_modelled() -> None:
    """An empty ability list means 'it does nothing', not 'I have not seen it'."""
    catalogue = build(cards_in(PLAYABLE))
    assert catalogue.abilities(FOREST) == ()
    assert not catalogue.modelled(FOREST)


def test_a_vanilla_card_in_the_fixture_is_modelled() -> None:
    assert Catalogue(rules={"vanilla": ()}).modelled(OracleId("vanilla"))


def test_a_card_with_an_unmodelled_ability_is_not() -> None:
    assert not Catalogue(rules={"odd": (UNKNOWN_ABILITY,)}).modelled(OracleId("odd"))


def test_a_cards_printed_text_is_carried_for_quoting() -> None:
    """R07: the text was in the store all along and never reached a prompt."""
    catalogue = build(cards_in(PLAYABLE), EFFECTS)
    assert "{T}: Add {G}." in catalogue.text(FOREST)


def test_a_card_the_store_has_never_seen_has_no_text_on_file() -> None:
    """Empty, not raising: the coach's lookups report absence, they do not fail."""
    assert build(cards_in(PLAYABLE)).text(OracleId("nope")) == ""


def test_a_transform_cards_text_names_both_faces() -> None:
    """Half a card quoted verbatim looks like a whole card.

    A transform card has no top-level text at all -- both halves live on the
    faces -- so a prompt built from the front alone would quote one half and
    read as complete, which is the confident-wrong-answer shape this project
    exists to avoid. The fixture is unedited Scryfall JSON, because a
    hand-built two-faced card could not catch a wrong assumption about the
    real shape.
    """
    cards = list(cards_in(SAMPLE))
    two = next(card for card in cards if card.is_multifaced)
    said = build(cards).text(two.oracle_id)
    for face in two.faces:
        assert f"{face.name}:" in said
    assert two.faces[1].oracle_text in said
