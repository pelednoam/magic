"""Reading decklist files, including the documents we refuse."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgcoach.carddata.decks import DeckEntry, load_decklist, load_set_decks
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.core.ids import SetCode

DATA = Path(__file__).resolve().parent.parent.parent / "data"
FDN = SetCode("FDN")


def test_load_reads_every_field(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(
        json.dumps(
            {
                "key": "cats",
                "name": "Cats",
                "color": "W",
                "tutorial": True,
                "sources": ["https://example.test", 7],
                "cards": [{"name": "Plains", "quantity": 7}],
            }
        ),
        encoding="utf-8",
    )
    deck = load_decklist(path)
    assert deck.key == "cats"
    assert deck.name == "Cats"
    assert deck.tutorial
    assert deck.sources == ("https://example.test",), "non-strings are dropped"
    assert deck.entries == (DeckEntry("Plains", 7),)


def test_missing_optional_fields_default(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"key": "x"}), encoding="utf-8")
    deck = load_decklist(path)
    assert deck.name == "x"
    assert deck.color == ""
    assert not deck.tutorial
    assert deck.entries == ()


def test_a_non_object_document_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text("[1, 2]", encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="not a JSON object"):
        load_decklist(path)


def test_a_missing_key_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"name": "Cats"}), encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="'key'"):
        load_decklist(path)


def test_a_non_object_card_entry_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"key": "x", "cards": ["Plains"]}), encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="not an object"):
        load_decklist(path)


@pytest.mark.parametrize("quantity", [0, -1, 1.5, "7", None, True])
def test_a_bad_quantity_is_rejected(quantity: object, tmp_path: Path) -> None:
    """Zero and booleans included: neither is a number of physical cards."""
    path = tmp_path / "d.json"
    path.write_text(
        json.dumps({"key": "x", "cards": [{"name": "Plains", "quantity": quantity}]}),
        encoding="utf-8",
    )
    with pytest.raises(MalformedJsonError, match="positive integer"):
        load_decklist(path)


def test_an_entry_without_a_name_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "d.json"
    path.write_text(json.dumps({"key": "x", "cards": [{"quantity": 1}]}), encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="'name'"):
        load_decklist(path)


def test_decks_load_in_a_stable_order() -> None:
    decks = load_set_decks(DATA, FDN)
    assert [d.key for d in decks] == sorted(d.key for d in decks)
