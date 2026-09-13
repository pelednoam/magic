"""Reading printings: a card plus the set it was printed in."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.jsondata import as_array, as_object
from mtgcoach.carddata.scryfall import (
    MalformedCardError,
    printing_from_json,
    read_printings,
)

if TYPE_CHECKING:
    from mtgcoach.carddata.jsondata import JsonObject

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"


def _raw() -> list[JsonObject]:
    parsed: object = json.loads(FIXTURE.read_text(encoding="utf-8"))
    items = as_array(parsed)
    assert items is not None
    objects = [as_object(item) for item in items]
    return [obj for obj in objects if obj is not None]


def _by_name(name: str) -> JsonObject:
    return next(c for c in _raw() if str(c["name"]).startswith(name))


def test_printings_carry_the_set_from_the_document(tmp_path: Path) -> None:
    """The set comes from the card, never from what the caller asked for."""
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(_raw()), encoding="utf-8")
    pairs = list(read_printings(path))
    codes = {code for _, code in pairs}
    assert codes == {"FDN", "ECL", "HOB"}, "the fixture spans three sets"
    assert all(code.isupper() for code in codes), "Scryfall writes them lower case"


def test_read_printings_sniffs_a_json_array(tmp_path: Path) -> None:
    path = tmp_path / "array.json"
    path.write_text("\n\n  " + json.dumps(_raw()), encoding="utf-8")
    assert len(list(read_printings(path))) == len(_raw())


def test_read_printings_sniffs_jsonl(tmp_path: Path) -> None:
    path = tmp_path / "bulk.jsonl"
    body = "\n".join(json.dumps(obj) for obj in _raw())
    path.write_text(f"\n\n{body}\n", encoding="utf-8")
    assert len(list(read_printings(path))) == len(_raw())


def test_read_printings_on_an_empty_file(tmp_path: Path) -> None:
    path = tmp_path / "empty.json"
    path.write_text("   \n\n", encoding="utf-8")
    assert list(read_printings(path)) == []


def test_printings_jsonl_skips_punctuation_and_scalars(tmp_path: Path) -> None:
    path = tmp_path / "bulk.jsonl"
    path.write_text("[\n" + json.dumps(_by_name("Abrade")) + ",\n\n42\n]\n", encoding="utf-8")
    pairs = list(read_printings(path))
    assert [card.name for card, _ in pairs] == ["Abrade"]


def test_a_printing_without_a_set_is_rejected() -> None:
    obj = {k: v for k, v in _by_name("Abrade").items() if k != "set"}
    with pytest.raises(MalformedCardError, match="'set'"):
        printing_from_json(obj)


def test_printings_jsonl_skips_a_scalar_line(tmp_path: Path) -> None:
    """A true JSONL file -- no leading bracket -- with a stray scalar in it.

    Distinct from the array case above: `read_printings` sniffs the first
    character, so a file starting with `[` never reaches the line reader.
    """
    path = tmp_path / "bulk.jsonl"
    path.write_text(json.dumps(_by_name("Abrade")) + "\n42\n" + '"a string"\n', encoding="utf-8")
    pairs = list(read_printings(path))
    assert [card.name for card, _ in pairs] == ["Abrade"]
