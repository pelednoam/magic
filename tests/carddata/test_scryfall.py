"""Parsing real Scryfall JSON.

The fixture is eight unedited Scryfall card objects, chosen because each breaks
a different naive assumption: a vanilla creature, a land with an empty mana cost,
a creature whose power is ``*``, a multi-keyword legend, a transform card with no
top-level cost or text at all, and an adventure card whose top-level cost is the
combined string ``{3} // {1}{B}``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.jsondata import as_array, as_object
from mtgcoach.carddata.scryfall import (
    MalformedCardError,
    card_from_json,
    cards_in,
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


def test_the_whole_fixture_parses() -> None:
    cards = list(cards_in(FIXTURE))
    assert len(cards) == len(_raw())


def test_a_plain_creature() -> None:
    card = card_from_json(_by_name("Aegis Turtle"))
    assert card.front.mana_cost == "{U}"
    assert card.front.power == "0"
    assert card.front.toughness == "5"
    assert card.front.types.is_creature
    assert not card.is_multifaced


def test_power_is_a_string_because_star_is_a_real_value() -> None:
    card = card_from_json(_by_name("Consuming Aberration"))
    assert card.front.power == "*"
    assert card.front.toughness == "*"


def test_a_land_has_an_empty_cost_and_produces_mana() -> None:
    card = card_from_json(_by_name("Bloodfell Caves"))
    assert card.front.mana_cost == ""
    assert card.produced_mana == {"B", "R"}
    assert card.front.types.is_land


def test_keywords_are_carried_across() -> None:
    card = card_from_json(_by_name("Aurelia"))
    assert card.keywords == {"Flying", "Vigilance", "Haste"}


def test_a_transform_card_takes_its_cost_from_the_face() -> None:
    """The top level has no mana_cost or oracle_text at all -- both are None."""
    raw = _by_name("Trystan")
    assert raw.get("mana_cost") is None
    assert "oracle_text" not in raw

    card = card_from_json(raw)
    assert card.is_multifaced
    assert len(card.faces) == 2
    assert card.front.mana_cost == "{2}{G}"
    assert card.front.oracle_text != ""
    assert card.faces[1].mana_cost == ""
    assert card.faces[1].name != card.front.name


def test_an_adventure_card_does_not_inherit_the_combined_cost() -> None:
    """The top-level cost is `{3} // {1}{B}`: worse than missing, it parses."""
    raw = _by_name("My Precious")
    assert raw["mana_cost"] == "{3} // {1}{B}"

    card = card_from_json(raw)
    assert card.front.mana_cost == "{3}"
    assert card.faces[1].mana_cost == "{1}{B}"


def test_unknown_fields_are_ignored() -> None:
    obj: JsonObject = {**_by_name("Abrade"), "some_future_field": {"nested": True}}
    assert card_from_json(obj).name == "Abrade"


@pytest.mark.parametrize("missing", ["oracle_id", "name", "cmc"])
def test_a_card_missing_an_essential_field_is_rejected(missing: str) -> None:
    obj = {k: v for k, v in _by_name("Abrade").items() if k != missing}
    with pytest.raises(MalformedCardError, match=missing):
        card_from_json(obj)


def test_an_absent_layout_defaults_to_normal() -> None:
    obj = {k: v for k, v in _by_name("Abrade").items() if k != "layout"}
    assert card_from_json(obj).layout == "normal"


def test_jsonl_streaming(tmp_path: Path) -> None:
    """Scryfall's bulk file is one object per line, too big to load at once."""
    path = tmp_path / "bulk.jsonl"
    path.write_text("\n".join(json.dumps(obj) for obj in _raw()) + "\n", encoding="utf-8")
    assert len(list(cards_in(path))) == len(_raw())


def test_jsonl_tolerates_array_punctuation(tmp_path: Path) -> None:
    """Some bulk dumps wrap the lines in brackets and end each with a comma."""
    path = tmp_path / "bulk.json"
    body = ",\n".join(json.dumps(obj) for obj in _raw())
    path.write_text(f"[\n{body}\n]\n", encoding="utf-8")
    assert len(list(cards_in(path))) == len(_raw())


def test_jsonl_skips_blank_lines(tmp_path: Path) -> None:
    path = tmp_path / "bulk.jsonl"
    path.write_text(json.dumps(_by_name("Abrade")) + "\n\n\n", encoding="utf-8")
    assert len(list(cards_in(path))) == 1


def test_non_object_entries_in_an_array_are_skipped(tmp_path: Path) -> None:
    """A bulk file with a stray scalar should import what it can."""
    path = tmp_path / "mixed.json"
    path.write_text(json.dumps(["not a card", 42, None, _by_name("Abrade")]), encoding="utf-8")
    cards = list(cards_in(path))
    assert len(cards) == 1
    assert cards[0].name == "Abrade"


def test_a_document_that_is_not_a_card_is_reported(tmp_path: Path) -> None:
    """The streaming reader finds the object; the card parser rejects it."""
    path = tmp_path / "object.json"
    path.write_text(json.dumps({"object": "error"}), encoding="utf-8")
    with pytest.raises(MalformedCardError, match="'name'"):
        list(cards_in(path))


def test_jsonl_skips_non_object_lines(tmp_path: Path) -> None:
    path = tmp_path / "bulk.jsonl"
    path.write_text(
        "\n".join(["42", '"a string"', json.dumps(_by_name("Abrade"))]) + "\n",
        encoding="utf-8",
    )
    cards = list(cards_in(path))
    assert len(cards) == 1
    assert cards[0].name == "Abrade"
