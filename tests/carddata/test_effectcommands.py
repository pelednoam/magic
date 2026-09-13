"""extract, review, seal, check -- driven with a fake extractor.

No test here invokes a model. That is the point of the ``EffectExtractor``
protocol: the expensive, slow, non-deterministic part is a seam, so everything
around it can be tested in milliseconds.
"""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from helpers import FakeExtractor
from mtgcoach.carddata import effectcommands
from mtgcoach.carddata.paths import set_dir
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.sealed import CardAbilities, dump
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.abilities import ActivatedAbility, UnmodeledAbility
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.ids import OracleId, SetCode
from mtgcoach.core.vocabulary import AbilityCost

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"
FDN = SetCode("FDN")
SAMPLE = 8

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
    elif command == "review":
        code = effectcommands.review(data, FDN, out)
    elif command == "seal":
        code = effectcommands.seal(data, FDN, out, "test-model", accepted=True)
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


def test_review_prints_nothing_extra_for_a_confident_modelled_card(
    data: Path,
) -> None:
    """Only the unmodelled and the doubtful earn a reviewer's attention."""
    target = set_dir(data, FDN)
    target.mkdir(parents=True, exist_ok=True)
    dump(
        target / effectcommands.PROPOSALS,
        [CardAbilities(OracleId("a"), "Clear", (MANA,), "", "high")],
    )
    code, out = run("review", data)
    assert code == 0
    assert "Clear" not in out
    assert "1/1 cards fully modelled" in out


def test_a_doubtful_card_without_notes_still_appears(data: Path) -> None:
    """Low confidence is worth surfacing even when the model said nothing more."""
    target = set_dir(data, FDN)
    target.mkdir(parents=True, exist_ok=True)
    dump(
        target / effectcommands.PROPOSALS,
        [CardAbilities(OracleId("a"), "Terse", (MANA,), "", "low")],
    )
    code, out = run("review", data)
    assert code == 0
    assert "Terse" in out
