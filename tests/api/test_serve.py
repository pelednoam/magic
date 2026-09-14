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
from typing import TYPE_CHECKING

import pytest

from helpers_api import talking
from mtgcoach.api.serve import assemble, main
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode
from wire import decoded, rows, words

if TYPE_CHECKING:
    from fastapi.testclient import TestClient

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
    serving = assemble(_stocked(tmp_path), DATA, FDN)
    with talking(serving.app, token=serving.token) as client:
        listed = decoded(client.get("/decks").json())
        assert "cats" in words(listed, "decks"), "the box decklists are on disk"


def test_a_deck_is_dealt_from_the_cards_the_store_actually_has(tmp_path: Path) -> None:
    """A partial import gives a short deck, not a refusal or a blank card."""
    serving = assemble(_stocked(tmp_path), DATA, FDN)
    with talking(serving.app, token=serving.token) as client:
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
    """A server assembled from a stocked database and this data root.

    It made its own token when it was assembled -- see `access.token_at` -- and
    hands it back, so the client is given that rather than the tests' fixed
    one.
    """
    serving = assemble(_stocked(tmp_path), data_root, FDN)
    return talking(serving.app, token=serving.token)


def test_the_rules_are_loaded_when_they_are_installed(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "data"
    _install_rules(root, _long_enough())
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


@pytest.mark.parametrize(
    "installed",
    [
        pytest.param("<html>404</html>", id="the HTML of an error page"),
        pytest.param(
            (FIXTURES / "rules_excerpt.txt").read_text(encoding="utf-8"),
            id="a download that stopped early",
        ),
    ],
)
def test_a_rules_document_that_is_not_the_rules_does_not_stop_the_server(
    installed: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Catching only "not installed" turned this into a stack trace at startup.

    A bad download stopped the tracker working at all -- over a feature the
    tracker does not need. The second case is the subtle one: it is genuinely
    rules-shaped, just far too little of it, and it used to be indexed and
    advertised as the Comprehensive Rules.
    """
    root = tmp_path / "data"
    _install_rules(root, installed)
    _copy_sets(root)
    with _dealt(tmp_path, root) as client:
        body = decoded(client.post("/games", json={"you": "elves", "them": "elves"}).json())
        assert body["rules_available"] is False
    assert "rules questions are off" in capsys.readouterr().out


def _copy_sets(root: Path) -> None:
    """The real per-set data, so `assemble` has decks to deal."""
    shutil.copytree(DATA / "sets", root / "sets", dirs_exist_ok=True)


def _install_rules(root: Path, document: str) -> None:
    """Put a rules document where `assemble` will look for it."""
    where = root / "rules" / "comprehensive.txt"
    where.parent.mkdir(parents=True, exist_ok=True)
    where.write_text(document, encoding="utf-8")


def _long_enough() -> str:
    """A rules-shaped document with enough in it to be believed.

    Generated rather than vendored: the real one is a megabyte of Wizards'
    text, and what this test needs is the shape and the size, not the content.
    """
    rules = [f"100.{n}. Rule number {n} says something about the game." for n in range(1, 900)]
    return "\n\n".join(
        [
            "Contents",
            "Glossary",
            "Credits",
            "1. Game Concepts",
            "100. General",
            *rules,
            "Glossary",
            "Trample",
            "A keyword ability.",
            "Credits",
            "Published by someone.",
        ]
    )
