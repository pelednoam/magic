"""Sealing and checking -- the step where data crosses into the engine."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from helpers import FakeExtractor
from mtgcoach.carddata import effectcommands
from mtgcoach.carddata import manifest as manifest_mod
from mtgcoach.carddata.paths import effects_path, manifest_path, set_dir
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.sealed import CardAbilities, dump
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.abilities import ActivatedAbility, UnmodeledAbility
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.ids import OracleId, SetCode
from mtgcoach.core.vocabulary import AbilityCost

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"
FDN = SetCode("FDN")
MANA = ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),))
UNKNOWN = UnmodeledAbility("Choose one", "modal spells are not modelled")


@pytest.fixture
def store() -> CardStore:
    loaded = CardStore.open()
    loaded.add((card, FDN) for card in cards_in(FIXTURE))
    return loaded


@pytest.fixture
def data(tmp_path: Path) -> Path:
    return tmp_path / "data"


def run(command: str, data: Path, store: CardStore | None = None) -> tuple[int, str]:
    out = io.StringIO()
    if command == "extract":
        assert store is not None
        code = effectcommands.extract(store, FakeExtractor(), data, FDN, out)
    elif command == "seal":
        code = effectcommands.seal(data, FDN, out, "test-model", accepted=True)
    elif command == "review":
        code = effectcommands.review(data, FDN, out)
    else:
        code = effectcommands.check(data, FDN, out)
    return code, out.getvalue()


def test_seal_needs_an_extraction_first(data: Path) -> None:
    code, out = run("seal", data)
    assert code == 1
    assert "nothing to seal" in out


def test_seal_writes_the_fixture_and_its_manifest(store: CardStore, data: Path) -> None:
    run("extract", data, store)
    code, out = run("seal", data)
    assert code == 0
    assert "sealed 8 cards" in out
    assert effects_path(data, FDN).exists()
    assert manifest_path(data, FDN).exists()


def test_check_passes_on_a_freshly_sealed_set(store: CardStore, data: Path) -> None:
    run("extract", data, store)
    run("seal", data)
    code, out = run("check", data)
    assert code == 0
    assert "matches its manifest" in out


def test_check_catches_a_tampered_fixture(store: CardStore, data: Path) -> None:
    """Editing the fixture without resealing must not go unnoticed."""
    run("extract", data, store)
    run("seal", data)
    path = effects_path(data, FDN)
    body = json.loads(path.read_text())
    body["cards"].pop()
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    code, out = run("check", data)
    assert code == 1
    assert "checksum mismatch" in out
    assert "manifest says" in out


def test_check_needs_a_sealed_set(data: Path) -> None:
    code, out = run("check", data)
    assert code == 1
    assert "never been sealed" in out


def test_sealing_is_the_only_way_data_crosses(store: CardStore, data: Path) -> None:
    """Extraction alone must not produce anything the engine would read."""
    run("extract", data, store)
    assert not effects_path(data, FDN).exists()
    run("seal", data)
    assert effects_path(data, FDN).exists()


def test_review_only_prints_reasons_for_the_unmodelled_parts(data: Path) -> None:
    """A card can be partly modelled; only the unmodelled abilities have reasons."""
    target = set_dir(data, FDN)
    target.mkdir(parents=True, exist_ok=True)
    dump(
        target / effectcommands.PROPOSALS,
        [CardAbilities(OracleId("x"), "Mixed", (MANA, UNKNOWN))],
    )
    code, out = run("review", data)
    assert code == 0
    assert "modal spells are not modelled" in out
    assert out.count("                ") == 1, "one reason, not one line per ability"


def test_seal_refuses_without_an_explicit_acceptance(store: CardStore, data: Path) -> None:
    """Sealing is the human step, so it has to be taken deliberately.

    The fixture is marked generated, so unreviewed model output reaching the
    engine would not show up in a diff either.
    """
    run("extract", data, store)
    out = io.StringIO()
    code = effectcommands.seal(data, FDN, out, "test-model")
    assert code == 1
    assert "review FDN first" in out.getvalue()
    assert "--accept" in out.getvalue()
    assert not effects_path(data, FDN).exists()


def test_the_manifest_records_which_model_produced_the_fixture(
    store: CardStore, data: Path
) -> None:
    """A sealed fixture that cannot say what made it cannot be reproduced."""
    run("extract", data, store)
    run("seal", data)
    assert manifest_mod.read(manifest_path(data, FDN)).model == "test-model"


def test_review_surfaces_the_doubtful_as_well_as_the_unmodelled(data: Path) -> None:
    """Confidence exists to put the uncertain ones in front of a person."""
    target = set_dir(data, FDN)
    target.mkdir(parents=True, exist_ok=True)
    dump(
        target / effectcommands.PROPOSALS,
        [
            CardAbilities(OracleId("a"), "Sure", (MANA,), "", "high"),
            CardAbilities(OracleId("b"), "Unsure", (MANA,), "guessed", "low"),
        ],
    )
    code, out = run("review", data)
    assert code == 0
    assert "Unsure" in out
    assert "guessed" in out
    assert "Sure" not in out.replace("Unsure", "")
