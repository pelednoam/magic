"""The card database."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgcoach.carddata.collection import Collection
from mtgcoach.carddata.schema import SchemaError, as_real, as_string_set, as_text
from mtgcoach.carddata.scryfall import cards_from_json_array
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import OracleId, SetCode

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"
FDN = SetCode("FDN")
BLB = SetCode("BLB")
SAMPLE_SIZE = 8


@pytest.fixture
def store() -> CardStore:
    loaded = CardStore.open()
    loaded.add((card, FDN) for card in cards_from_json_array(FIXTURE))
    return loaded


def test_cards_round_trip(store: CardStore) -> None:
    original = {c.oracle_id: c for c in cards_from_json_array(FIXTURE)}
    for oracle_id, expected in original.items():
        assert store.get(oracle_id) == expected


def test_a_transform_card_keeps_both_faces(store: CardStore) -> None:
    """The shape that top-level fields cannot express survives storage."""
    card = store.by_name("Trystan, Callous Cultivator // Trystan, Penitent Culler")
    assert card is not None
    assert len(card.faces) == 2
    assert card.front.mana_cost == "{2}{G}"
    assert card.faces[1].mana_cost == ""


def test_a_missing_card_is_none(store: CardStore) -> None:
    assert store.get(OracleId("nope")) is None
    assert store.by_name("Nonesuch") is None


def test_reimporting_is_idempotent(store: CardStore) -> None:
    """The bulk file refreshes daily; re-importing is the normal update path."""
    before = store.count_in(FDN)
    store.add((card, FDN) for card in cards_from_json_array(FIXTURE))
    assert store.count_in(FDN) == before


def test_reimporting_replaces_faces_rather_than_appending(store: CardStore) -> None:
    card = store.by_name("Trystan, Callous Cultivator // Trystan, Penitent Culler")
    assert card is not None
    store.add([(card, FDN)])
    again = store.get(card.oracle_id)
    assert again is not None
    assert len(again.faces) == 2


def test_set_codes_and_counts(store: CardStore) -> None:
    assert store.set_codes() == (FDN,)
    assert store.count_in(FDN) == SAMPLE_SIZE
    assert store.count_in(BLB) == 0


def test_names_in_a_set(store: CardStore) -> None:
    names = store.names_in(FDN)
    assert "Abrade" in names
    assert len(names) == SAMPLE_SIZE
    assert store.names_in(BLB) == frozenset()


def test_cards_in_a_set_are_ordered_by_name(store: CardStore) -> None:
    names = [c.name for c in store.cards_in_set(FDN)]
    assert names == sorted(names)
    assert len(names) == SAMPLE_SIZE


def test_the_same_card_can_belong_to_two_sets(store: CardStore) -> None:
    """A reprint is one oracle card with two printings, not two cards."""
    abrade = store.by_name("Abrade")
    assert abrade is not None
    store.add([(abrade, BLB)])
    assert store.count_in(FDN) == SAMPLE_SIZE
    assert store.count_in(BLB) == 1
    assert len(store.cards_in(Collection(sets=frozenset({FDN, BLB})))) == SAMPLE_SIZE


def test_an_empty_collection_scopes_to_nothing(store: CardStore) -> None:
    assert store.cards_in(Collection()) == ()


def test_a_collection_of_singles(store: CardStore) -> None:
    abrade = store.by_name("Abrade")
    assert abrade is not None
    scoped = store.cards_in(Collection(extra_cards=frozenset({abrade.oracle_id})))
    assert [c.name for c in scoped] == ["Abrade"]


def test_the_collection_persists(store: CardStore) -> None:
    assert store.collection().is_empty
    store.enable_set(FDN)
    store.enable_set(FDN)
    assert store.collection().sets == {FDN}
    store.disable_set(FDN)
    assert store.collection().is_empty


def test_disabling_a_set_keeps_its_cards(store: CardStore) -> None:
    store.enable_set(FDN)
    store.disable_set(FDN)
    assert store.count_in(FDN) == SAMPLE_SIZE


def test_a_file_backed_store_survives_reopening(tmp_path: Path) -> None:
    path = str(tmp_path / "cards.sqlite3")
    with CardStore.open(path) as first:
        first.add((card, FDN) for card in cards_from_json_array(FIXTURE))
        first.enable_set(FDN)
    with CardStore.open(path) as second:
        assert second.count_in(FDN) == SAMPLE_SIZE
        assert second.collection().sets == {FDN}


def test_a_row_of_the_wrong_type_is_reported() -> None:
    """The schema promises types; a violated promise must not pass silently."""
    with pytest.raises(SchemaError, match="should be text"):
        as_text(7, "name")
    with pytest.raises(SchemaError, match="should be numeric"):
        as_real("x", "cmc")
    truthy: object = True
    with pytest.raises(SchemaError, match="should be numeric"):
        as_real(truthy, "cmc")
    with pytest.raises(SchemaError, match="JSON array"):
        as_string_set(json.dumps({"a": 1}), "keywords")
