"""Battlefield-only state."""

from __future__ import annotations

from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent

CARD = CardInstance(InstanceId("x"), OracleId("o"))


def test_a_new_permanent_is_untapped_and_summoning_sick() -> None:
    permanent = Permanent(CARD)
    assert not permanent.tapped
    assert permanent.summoning_sick


def test_instance_id_delegates_to_the_card() -> None:
    assert Permanent(CARD).instance_id == InstanceId("x")


def test_tap_and_untap_return_new_values() -> None:
    permanent = Permanent(CARD)
    tapped = permanent.tap()
    assert tapped.tapped
    assert not permanent.tapped, "the original must be unchanged"
    assert not tapped.untap().tapped


def test_settle_clears_summoning_sickness() -> None:
    assert not Permanent(CARD).settle().summoning_sick


def test_tapping_preserves_the_other_fields() -> None:
    permanent = Permanent(CARD).settle()
    assert not permanent.tap().summoning_sick
