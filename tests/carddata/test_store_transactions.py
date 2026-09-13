"""Transactions, and the cost of reading a set."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata import schema
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import SetCode

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.carddata.cards import Card

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"
FDN = SetCode("FDN")
SAMPLE_SIZE = 8


def _cards_then_fail(n: int) -> Iterator[tuple[Card, SetCode]]:
    """Yield some cards and then fail, as a bad row in a bulk file would."""
    for i, card in enumerate(cards_in(FIXTURE)):
        if i == n:
            msg = "malformed card part-way through the file"
            raise RuntimeError(msg)
        yield card, FDN


def test_an_import_that_fails_part_way_writes_nothing(tmp_path: Path) -> None:
    """add() is one transaction, so a half-finished import leaves no half-set."""
    path = str(tmp_path / "cards.sqlite3")
    with CardStore.open(path) as store, pytest.raises(RuntimeError):
        store.add(_cards_then_fail(3))

    with CardStore.open(path) as after:
        assert after.count_in(FDN) == 0


def test_a_successful_command_commits(tmp_path: Path) -> None:
    path = str(tmp_path / "cards.sqlite3")
    with CardStore.open(path) as store:
        store.add((card, FDN) for card in cards_in(FIXTURE))
    with CardStore.open(path) as after:
        assert after.count_in(FDN) == SAMPLE_SIZE


def test_leaving_the_context_with_an_exception_rolls_back() -> None:
    """Exercise the context-manager contract directly.

    Every write method opens its own transaction, so this branch is insurance
    against a future one that forgets to.
    """
    store = CardStore.open()
    store.add((card, FDN) for card in cards_in(FIXTURE))
    store.__exit__(RuntimeError, RuntimeError("boom"), None)
    with pytest.raises(sqlite3.ProgrammingError):
        store.count_in(FDN)


def test_reading_a_set_takes_a_constant_number_of_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One face query per card made every bulk read N+1 -- 518 for a real set."""
    counts = {"n": 0}
    original = schema.rows

    def counting(*args: object, **kwargs: object) -> list[tuple[object, ...]]:
        counts["n"] += 1
        return original(*args, **kwargs)  # type: ignore[arg-type]

    with CardStore.open() as loaded:
        loaded.add((card, FDN) for card in cards_in(FIXTURE))
        monkeypatch.setattr(schema, "rows", counting)
        cards = loaded.cards_in_set(FDN)

    assert len(cards) == SAMPLE_SIZE
    assert counts["n"] == 2, "one query for the cards, one for all their faces"
    assert any(len(c.faces) == 2 for c in cards), "multi-face cards survived"


def test_abort_discards_uncommitted_work(tmp_path: Path) -> None:
    path = str(tmp_path / "cards.sqlite3")
    store = CardStore.open(path)
    store.add((card, FDN) for card in cards_in(FIXTURE))
    store.abort()
    with CardStore.open(path) as after:
        assert after.count_in(FDN) == SAMPLE_SIZE, "add() commits its own transaction"
