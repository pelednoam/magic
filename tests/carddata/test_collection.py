"""What cards you own."""

from __future__ import annotations

from mtgcoach.carddata.collection import Collection
from mtgcoach.core.ids import OracleId, SetCode

FDN = SetCode("FDN")
BLB = SetCode("BLB")
SINGLE = OracleId("f84c30e7-2ea8-43ff-9356-1f907558cfd9")


def test_a_new_collection_is_empty() -> None:
    assert Collection().is_empty


def test_owning_a_set_is_not_empty() -> None:
    assert not Collection().with_set(FDN).is_empty


def test_owning_a_single_is_not_empty() -> None:
    assert not Collection().with_card(SINGLE).is_empty


def test_adding_a_set_returns_a_new_collection() -> None:
    first = Collection()
    second = first.with_set(FDN)
    assert second.sets == {FDN}
    assert first.sets == frozenset(), "the original must be unchanged"


def test_sets_accumulate() -> None:
    assert Collection().with_set(FDN).with_set(BLB).sets == {FDN, BLB}


def test_adding_a_set_twice_changes_nothing() -> None:
    once = Collection().with_set(FDN)
    assert once.with_set(FDN) == once


def test_singles_accumulate_separately_from_sets() -> None:
    collection = Collection().with_set(FDN).with_card(SINGLE)
    assert collection.sets == {FDN}
    assert collection.extra_cards == {SINGLE}
