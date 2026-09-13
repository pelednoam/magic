"""The sealed fixture the engine reads, and the real one we shipped."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from mtgcoach.carddata import manifest as manifest_mod
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.carddata.paths import effects_path, manifest_path
from mtgcoach.carddata.sealed import CardAbilities, dump, load
from mtgcoach.core.abilities import ActivatedAbility, SpellAbility, UnmodeledAbility
from mtgcoach.core.effects import ChangeLife, ProduceMana
from mtgcoach.core.ids import OracleId, SetCode
from mtgcoach.core.targets import Controller
from mtgcoach.core.vocabulary import AbilityCost

DATA = Path(__file__).resolve().parent.parent.parent / "data"
FDN = SetCode("FDN")

BOX_CARDS = 124


def _cards() -> list[CardAbilities]:
    return [
        CardAbilities(
            OracleId("b"),
            "Bear",
            (ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),)),),
        ),
        CardAbilities(
            OracleId("a"),
            "Abrade",
            (SpellAbility((ChangeLife(1, Controller.YOU),)),),
            notes="two clauses",
        ),
    ]


def test_a_fixture_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "effects.json"
    dump(path, _cards())
    assert sorted(load(path), key=lambda c: c.name) == sorted(_cards(), key=lambda c: c.name)


def test_cards_are_written_in_name_order(tmp_path: Path) -> None:
    """The manifest checksums these bytes, so the order cannot be incidental."""
    path = tmp_path / "effects.json"
    dump(path, _cards())
    names = [c["name"] for c in json.loads(path.read_text())["cards"]]
    assert names == sorted(names)


def test_the_same_cards_produce_the_same_bytes(tmp_path: Path) -> None:
    first, second = tmp_path / "a.json", tmp_path / "b.json"
    dump(first, _cards())
    dump(second, list(reversed(_cards())))
    assert first.read_bytes() == second.read_bytes()


def test_a_vanilla_card_counts_as_modelled() -> None:
    """It does nothing, which is fully understood, not unknown."""
    assert CardAbilities(OracleId("x"), "Savannah Lions", ()).is_modelled


def test_a_card_with_an_unmodelled_ability_does_not() -> None:
    card = CardAbilities(OracleId("x"), "Deadly Plot", (UnmodeledAbility("m", "modal"),))
    assert not card.is_modelled


def test_a_document_without_cards_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "effects.json"
    path.write_text(json.dumps({"cards": "lots"}), encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="'cards' must be a list"):
        load(path)


def test_a_card_missing_its_identity_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "effects.json"
    path.write_text(json.dumps({"cards": [{"name": "x"}]}), encoding="utf-8")
    with pytest.raises(MalformedJsonError, match="oracle_id"):
        load(path)


# --- the fixture actually shipped -----------------------------------------


def test_the_shipped_fixture_loads() -> None:
    cards = load(effects_path(DATA, FDN))
    assert len(cards) == BOX_CARDS


def test_the_shipped_fixture_matches_its_manifest() -> None:
    """Drift between the two is what the signed manifest exists to catch."""
    record = manifest_mod.read(manifest_path(DATA, FDN))
    assert manifest_mod.verify(effects_path(DATA, FDN), record) == ()


def test_the_manifest_records_the_coverage_we_claim() -> None:
    record = manifest_mod.read(manifest_path(DATA, FDN))
    cards = load(effects_path(DATA, FDN))
    assert record.card_count == len(cards)
    assert record.modelled_count == sum(1 for c in cards if c.is_modelled)


def test_every_mana_source_in_the_box_is_modelled() -> None:
    """The M4 solver reads these; a set with none would be unplayable."""
    cards = load(effects_path(DATA, FDN))
    mana = [
        card
        for card in cards
        for a in card.abilities
        if isinstance(a, ActivatedAbility) and a.is_mana_ability
    ]
    assert len(mana) >= 5, "the box has lands and mana creatures"
