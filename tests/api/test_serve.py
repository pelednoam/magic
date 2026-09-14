# pyright: reportUnknownMemberType=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
#
# Starlette's TestClient is typed loosely enough that strict pyright cannot see
# through it; everything it returns here is narrowed by ``wire``.

"""Assembling the real server from what is on disk.

The one module that reads from disk, so the one that can fail on a machine
where the data was never imported -- which is exactly the failure a person
meets first, and the one worth a sentence rather than a stack trace.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mtgcoach.api.serve import assemble, main
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode
from wire import decoded, rows, words

FIXTURES = Path(__file__).resolve().parent.parent / "fixtures"
PLAYABLE = FIXTURES / "scryfall_fdn_playable.json"
DATA = Path(__file__).resolve().parents[2] / "data"
FDN = SetCode("FDN")
HTTP_OK = 200


def _stocked(tmp_path: Path) -> Path:
    """A card database with the playable fixture imported."""
    db = tmp_path / "cards.sqlite3"
    with CardStore.open(str(db)) as store:
        store.add((card, FDN) for card in cards_in(PLAYABLE))
    return db


def test_a_server_built_from_disk_deals_the_sets_decks(tmp_path: Path) -> None:
    app = assemble(_stocked(tmp_path), DATA, FDN)
    with TestClient(app) as client:
        listed = decoded(client.get("/decks").json())
        assert "cats" in words(listed, "decks"), "the box decklists are on disk"


def test_a_deck_is_dealt_from_the_cards_the_store_actually_has(tmp_path: Path) -> None:
    """A partial import gives a short deck, not a refusal or a blank card."""
    app = assemble(_stocked(tmp_path), DATA, FDN)
    with TestClient(app) as client:
        response = client.post("/games", json={"you": "elves", "them": "elves"})
        assert response.status_code == HTTP_OK, response.text
        hand = rows(decoded(response.json()), "state", "players", "you", "hand")
        assert hand, "a deck built from the store deals a real opening hand"


def test_an_empty_database_says_what_to_run(tmp_path: Path) -> None:
    """A coach with no cards looks broken unless it says what is missing."""
    empty = tmp_path / "empty.sqlite3"
    with CardStore.open(str(empty)):
        pass
    with pytest.raises(ValueError, match="run `mtgcoach sets add FDN` first"):
        assemble(empty, DATA, FDN)


def test_the_command_line_serves(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Parsed and wired, without actually binding a port."""
    served: list[tuple[str, int]] = []

    def record(_app: object, *, host: str, port: int) -> None:
        served.append((host, port))

    monkeypatch.setattr("mtgcoach.api.serve.uvicorn.run", record)
    code = main(["--db", str(_stocked(tmp_path)), "--data", str(DATA), "--port", "9999"])
    assert code == 0
    assert served == [("0.0.0.0", 9999)]  # noqa: S104 - serving the LAN is the point


def _dealt(tmp_path: Path, data_root: Path) -> TestClient:
    """A server assembled from a stocked database and this data root."""
    return TestClient(assemble(_stocked(tmp_path), data_root, FDN))


def test_the_rules_are_loaded_when_they_are_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "data"
    (root / "rules").mkdir(parents=True)
    excerpt = FIXTURES / "rules_excerpt.txt"
    (root / "rules" / "comprehensive.txt").write_text(
        excerpt.read_text(encoding="utf-8"), encoding="utf-8"
    )
    _copy_sets(root)
    with _dealt(tmp_path, root) as client:
        body = decoded(client.post("/games", json={"you": "elves", "them": "elves"}).json())
        assert body["rules_available"] is True
    assert "rules questions are off" not in capsys.readouterr().out


def test_a_server_without_the_rules_still_starts(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The tracker, the engine and the turn coach all work without them."""
    root = tmp_path / "data"
    _copy_sets(root)
    with _dealt(tmp_path, root) as client:
        body = decoded(client.post("/games", json={"you": "elves", "them": "elves"}).json())
        assert body["rules_available"] is False
    # Printed, because a question box that silently answers nothing is worse
    # than one that says it is switched off.
    assert "rules questions are off" in capsys.readouterr().out


def test_a_rules_document_that_is_not_the_rules_does_not_stop_the_server(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A truncated download, or the HTML of an error page.

    Catching only "not installed" turned that into a stack trace at startup, so
    a bad download stopped the tracker working at all -- over a feature the
    tracker does not need.
    """
    root = tmp_path / "data"
    (root / "rules").mkdir(parents=True)
    (root / "rules" / "comprehensive.txt").write_text("<html>404</html>", encoding="utf-8")
    _copy_sets(root)
    with _dealt(tmp_path, root) as client:
        body = decoded(client.post("/games", json={"you": "elves", "them": "elves"}).json())
        assert body["rules_available"] is False
    assert "rules questions are off" in capsys.readouterr().out


def _copy_sets(root: Path) -> None:
    """The real per-set data, so `assemble` has decks to deal."""
    shutil.copytree(DATA / "sets", root / "sets", dirs_exist_ok=True)
