"""`sets fetch`, with Scryfall replaced.

The one command that touches the network, so the one whose test has to prove it
does not: ``HttpPages.fetch`` is replaced throughout, and the plugin in
``tests/noclaude.py`` would refuse a subprocess anyway.

What matters here is the whole path a person actually follows -- fetch, then
add -- because that is the pair that was missing. The importer has always
worked; there was no way to get it a file.
"""

from __future__ import annotations

import io
import json
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.cli import main
from mtgcoach.carddata.scryfallapi import ScryfallError
from mtgcoach.carddata.scryfallhttp import HttpPages

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.carddata.jsondata import JsonObject

#: Two real-enough cards. `sets add` reads these with the real reader, so they
#: carry the fields it requires.
CARDS: list[JsonObject] = [
    {
        "object": "card",
        "oracle_id": "b34bb2dc-c1af-4d77-b0b3-a0fb342a5fc6",
        "name": "Forest",
        "set": "fdn",
        "cmc": 0.0,
        "type_line": "Basic Land — Forest",
        "oracle_text": "({T}: Add {G}.)",
        "produced_mana": ["G"],
    },
    {
        "object": "card",
        "oracle_id": "68954295-54e3-4303-a6bc-fc4547a4e3a3",
        "name": "Llanowar Elves",
        "set": "fdn",
        "cmc": 1.0,
        "mana_cost": "{G}",
        "type_line": "Creature — Elf Druid",
        "oracle_text": "{T}: Add {G}.",
        "power": "1",
        "toughness": "1",
        "colors": ["G"],
    },
]


def _answering(*pages: JsonObject) -> object:
    """A replacement `fetch` that hands back these pages in order."""
    remaining = list(pages)

    def fetch(_self: HttpPages, _url: str) -> JsonObject:
        if not remaining:
            msg = "asked for more pages than the test prepared"
            raise ScryfallError(msg)
        return remaining.pop(0)

    return fetch


def _run(*argv: str, db: Path, data: Path) -> tuple[int, str]:
    out = io.StringIO()
    code = main(["--db", str(db), "--data", str(data), *argv], out=out)
    return code, out.getvalue()


@pytest.fixture
def scryfall(monkeypatch: pytest.MonkeyPatch) -> None:
    """One page carrying both cards."""
    page: JsonObject = {"object": "list", "has_more": False, "data": list(CARDS)}
    monkeypatch.setattr(HttpPages, "fetch", _answering(page))


@pytest.mark.usefixtures("scryfall")
def test_fetch_writes_the_printings_where_add_can_find_them(tmp_path: Path) -> None:
    code, said = _run("sets", "fetch", "FDN", db=tmp_path / "cards.sqlite3", data=tmp_path)
    assert code == 0, said
    written = tmp_path / "scryfall" / "FDN.json"
    assert written.is_file()
    assert [c["name"] for c in json.loads(written.read_text())] == ["Forest", "Llanowar Elves"]


@pytest.mark.usefixtures("scryfall")
def test_fetch_says_what_to_run_next(tmp_path: Path) -> None:
    """The pair is the point, and nothing else in the CLI is two steps."""
    _, said = _run("sets", "fetch", "FDN", db=tmp_path / "cards.sqlite3", data=tmp_path)
    assert "sets add FDN --from" in said


@pytest.mark.usefixtures("scryfall")
def test_fetch_then_add_puts_real_cards_in_the_store(tmp_path: Path) -> None:
    """The whole path a person follows. This is what was missing."""
    db = tmp_path / "cards.sqlite3"
    assert _run("sets", "fetch", "FDN", db=db, data=tmp_path)[0] == 0
    code, said = _run(
        "sets",
        "add",
        "FDN",
        "--from",
        str(tmp_path / "scryfall" / "FDN.json"),
        db=db,
        data=tmp_path,
    )
    assert code == 0, said
    assert "2 FDN printings" in said
    assert "2 cards" in _run("sets", "list", db=db, data=tmp_path)[1]


@pytest.mark.usefixtures("scryfall")
def test_where_it_writes_can_be_chosen(tmp_path: Path) -> None:
    chosen = tmp_path / "elsewhere" / "cards.json"
    code, said = _run(
        "sets", "fetch", "FDN", "--to", str(chosen), db=tmp_path / "cards.sqlite3", data=tmp_path
    )
    assert code == 0, said
    assert chosen.is_file()


def test_a_set_scryfall_does_not_have_fails_with_its_reason(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    refusal: JsonObject = {"object": "error", "details": "Your query didn't match anything."}
    monkeypatch.setattr(HttpPages, "fetch", _answering(refusal))
    code, said = _run("sets", "fetch", "ZZZ", db=tmp_path / "cards.sqlite3", data=tmp_path)
    assert code != 0
    assert "didn't match anything" in said
    assert not (tmp_path / "scryfall").exists(), "nothing written for a failed fetch"


def test_a_set_with_no_printings_fails_rather_than_writing_an_empty_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An empty file would import as "no cards in it", one step too late."""
    empty: JsonObject = {"object": "list", "has_more": False, "data": []}
    monkeypatch.setattr(HttpPages, "fetch", _answering(empty))
    code, said = _run("sets", "fetch", "FDN", db=tmp_path / "cards.sqlite3", data=tmp_path)
    assert code != 0
    assert "no printings" in said
    assert not (tmp_path / "scryfall").exists()
