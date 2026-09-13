"""The command line, driven in-process.

``main`` takes its arguments and output stream as parameters, so every command
is exercised here without a subprocess -- which keeps the tests fast and lets
them assert on what the user actually sees.
"""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from mtgcoach.carddata.cli import main

REPO = Path(__file__).resolve().parent.parent.parent
FIXTURE = REPO / "tests" / "fixtures" / "scryfall_fdn_sample.json"
DECK_COUNT = 10

#: The fixture is eight real cards, but two were pulled from other sets so that
#: set filtering is exercised against real data rather than a contrived file.
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


def test_add_reports_printings_and_distinct_cards(db: Path) -> None:
    code, out = run("sets", "add", "FDN", "--from", str(FIXTURE), db=db)
    assert code == 0
    assert "6 FDN printings (6 distinct cards)" in out


def test_add_creates_the_database_directory(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b" / "cards.sqlite3"
    code, _ = run("sets", "add", "FDN", "--from", str(FIXTURE), db=nested)
    assert code == 0
    assert nested.exists()


def test_add_ignores_other_sets_in_the_file(db: Path, tmp_path: Path) -> None:
    """A bulk file spans every set; only the requested one may be imported."""
    relabelled = tmp_path / "other.json"
    cards = json.loads(FIXTURE.read_text())
    for card in cards:
        card["set"] = "blb"
    relabelled.write_text(json.dumps(cards))
    code, out = run("sets", "add", "FDN", "--from", str(relabelled), db=db)
    assert code == 1
    assert "no FDN cards" in out


def test_add_reads_jsonl_as_well_as_arrays(db: Path, tmp_path: Path) -> None:
    lines = tmp_path / "bulk.jsonl"
    cards = json.loads(FIXTURE.read_text())
    lines.write_text("\n".join(json.dumps(c) for c in cards) + "\n")
    code, out = run("sets", "add", "FDN", "--from", str(lines), db=db)
    assert code == 0
    assert "6 FDN printings" in out


def test_list_when_empty(db: Path) -> None:
    code, out = run("sets", "list", db=db)
    assert code == 0
    assert "no sets imported yet" in out


def test_list_marks_owned_sets(stocked: Path) -> None:
    _, before = run("sets", "list", db=stocked)
    assert "owned" not in before
    run("pool", "enable", "FDN", db=stocked)
    _, after = run("sets", "list", db=stocked)
    assert "owned" in after
    assert "FDN" in after


def test_audit_reports_unmodelled_mechanics(stocked: Path) -> None:
    code, out = run("sets", "audit", "FDN", db=stocked)
    assert code == 0
    assert f"FDN: {FDN_IN_FIXTURE} cards" in out
    assert "not modelled" in out
    assert "Flying (1 card)" in out, "singular, not '1 cards'"


def test_audit_of_an_unknown_set_fails(db: Path) -> None:
    code, out = run("sets", "audit", "BLB", db=db)
    assert code == 1
    assert "nothing imported" in out


def test_audit_reports_full_support_when_everything_is_modelled(db: Path, tmp_path: Path) -> None:
    vanilla = tmp_path / "vanilla.json"
    cards = [c for c in json.loads(FIXTURE.read_text()) if not c.get("keywords")]
    vanilla.write_text(json.dumps(cards))
    run("sets", "add", "FDN", "--from", str(vanilla), db=db)
    code, out = run("sets", "audit", "FDN", db=db)
    assert code == 0
    assert "every mechanic is modelled" in out
