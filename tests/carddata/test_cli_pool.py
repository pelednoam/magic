"""The pool and decks subcommands."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mtgcoach.carddata.cli import main
from mtgcoach.carddata.store import CardStore

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "scryfall_fdn_sample.json"
DECK_COUNT = 10
FDN_IN_FIXTURE = 6


def run(*argv: str, db: Path, data: Path | None = None) -> tuple[int, str]:
    out = io.StringIO()
    code = main(["--db", str(db), "--data", str(data or REPO / "data"), *argv], out=out)
    return code, out.getvalue()


@pytest.fixture
def db(tmp_path: Path) -> Path:
    return tmp_path / "cards.sqlite3"


@pytest.fixture
def stocked(db: Path) -> Path:
    run("sets", "add", "FDN", "--from", str(FIXTURE), db=db)
    return db


def test_pool_show_when_empty(db: Path) -> None:
    code, out = run("pool", "show", db=db)
    assert code == 0
    assert "nothing owned yet" in out


def test_pool_enable_requires_an_imported_set(db: Path) -> None:
    code, out = run("pool", "enable", "FDN", db=db)
    assert code == 1
    assert "not imported" in out


def test_pool_enable_then_show_then_disable(stocked: Path) -> None:
    assert run("pool", "enable", "FDN", db=stocked)[0] == 0
    code, out = run("pool", "show", db=stocked)
    assert code == 0
    assert "FDN" in out
    assert f"{FDN_IN_FIXTURE} cards in scope" in out
    assert run("pool", "disable", "FDN", db=stocked)[0] == 0
    assert "nothing owned yet" in run("pool", "show", db=stocked)[1]


def test_pool_show_lists_singles(stocked: Path) -> None:
    with CardStore.open(str(stocked)) as store:
        abrade = store.by_name("Abrade")
        assert abrade is not None
        store.enable_card(abrade.oracle_id)
    code, out = run("pool", "show", db=stocked)
    assert code == 0
    assert "single" in out


def test_decks_verify_needs_cards_first(db: Path) -> None:
    code, out = run("decks", "verify", "FDN", db=db)
    assert code == 1
    assert "cannot verify names" in out


def test_decks_verify_reports_a_set_with_no_decklists(stocked: Path, tmp_path: Path) -> None:
    empty = tmp_path / "emptydata"
    (empty / "sets" / "FDN" / "decks").mkdir(parents=True)
    code, out = run("decks", "verify", "FDN", db=stocked, data=empty)
    assert code == 1
    assert "no decklists shipped" in out


def test_decks_verify_flags_an_unverifiable_deck(stocked: Path) -> None:
    """Only eight cards are imported, so the real decklists cannot verify."""
    code, out = run("decks", "verify", "FDN", db=stocked)
    assert code == 1
    assert "PARTIAL" in out
    assert "not cards in this set" in out
    assert f"0/{DECK_COUNT} decklists verified" in out


def test_decks_verify_passes_against_the_full_set(tmp_path: Path) -> None:
    """The real check: every shipped decklist against every real FDN card."""
    names = json.loads((REPO / "tests" / "fixtures" / "fdn_card_names.json").read_text())
    export = tmp_path / "full.json"
    export.write_text(
        json.dumps(
            [
                {
                    "oracle_id": f"id-{i}",
                    "name": name,
                    "cmc": 0,
                    "set": "fdn",
                    "layout": "normal",
                }
                for i, name in enumerate(names)
            ]
        )
    )
    db = tmp_path / "full.sqlite3"
    assert run("sets", "add", "FDN", "--from", str(export), db=db)[0] == 0
    code, out = run("decks", "verify", "FDN", db=db)
    assert code == 0
    assert f"{DECK_COUNT}/{DECK_COUNT} decklists verified" in out


def test_a_malformed_set_code_is_rejected_before_any_io(db: Path) -> None:
    with pytest.raises(SystemExit):
        run("sets", "audit", "../etc", db=db)


def test_set_codes_are_accepted_in_lower_case(stocked: Path) -> None:
    code, out = run("sets", "audit", "fdn", db=stocked)
    assert code == 0
    assert f"FDN: {FDN_IN_FIXTURE} cards" in out
