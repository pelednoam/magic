"""extract, review, seal, check -- driven with a fake extractor.

No test here invokes a model. That is the point of the ``EffectExtractor``
protocol: the expensive, slow, non-deterministic part is a seam, so everything
around it can be tested in milliseconds.
"""

from __future__ import annotations

import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata import effectcommands
from mtgcoach.carddata.extraction import (
    Confidence,
    ExtractionResult,
    Proposal,
)
from mtgcoach.carddata.paths import effects_path, manifest_path, set_dir
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.sealed import CardAbilities, dump
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.abilities import ActivatedAbility, UnmodeledAbility
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.ids import OracleId, SetCode
from mtgcoach.core.vocabulary import AbilityCost

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.carddata.cards import Card

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"
FDN = SetCode("FDN")
SAMPLE = 8

MANA = ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),))
UNKNOWN = UnmodeledAbility("Choose one", "modal spells are not modelled")


@dataclass(frozen=True, slots=True)
class FakeExtractor:
    """Answers without a model. One card in three is left unmodelled."""

    failures: tuple[str, ...] = ()

    def extract(self, cards: Sequence[Card]) -> ExtractionResult:
        """Propose a mana ability for most cards and an unmodelled one for some."""
        proposals = tuple(
            Proposal(
                oracle_id=OracleId(card.oracle_id),
                name=card.name,
                abilities=(UNKNOWN,) if index % 3 == 0 else (MANA,),
                confidence=Confidence.HIGH,
                notes="",
            )
            for index, card in enumerate(cards)
        )
        return ExtractionResult(proposals, self.failures)


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
    elif command == "review":
        code = effectcommands.review(data, FDN, out)
    elif command == "seal":
        code = effectcommands.seal(data, FDN, out)
    else:
        code = effectcommands.check(data, FDN, out)
    return code, out.getvalue()


def test_extract_writes_proposals(store: CardStore, data: Path) -> None:
    code, out = run("extract", data, store)
    assert code == 0
    assert f"{SAMPLE} proposals written" in out
    assert (set_dir(data, FDN) / effectcommands.PROPOSALS).exists()


def test_extract_needs_cards_first(data: Path) -> None:
    out = io.StringIO()
    with CardStore.open() as empty:
        code = effectcommands.extract(empty, FakeExtractor(), data, FDN, out)
    assert code == 1
    assert "no FDN cards imported" in out.getvalue()


def test_extract_reports_problems(store: CardStore, data: Path) -> None:
    out = io.StringIO()
    code = effectcommands.extract(
        store, FakeExtractor(failures=("Bear: no proposal returned",)), data, FDN, out
    )
    assert code == 1
    assert "problem: Bear: no proposal returned" in out.getvalue()


def test_review_needs_an_extraction_first(data: Path) -> None:
    code, out = run("review", data)
    assert code == 1
    assert "nothing to review" in out


def test_review_names_the_unmodelled_cards(store: CardStore, data: Path) -> None:
    run("extract", data, store)
    code, out = run("review", data)
    assert code == 0
    assert "unmodelled" in out
    assert "modal spells are not modelled" in out
    assert "fully modelled" in out


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
