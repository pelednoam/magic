"""What a set would cost to support."""

from __future__ import annotations

from pathlib import Path

from mtgcoach.carddata.mechanics import SUPPORTED_KEYWORDS, audit
from mtgcoach.carddata.scryfall import cards_from_json_array
from mtgcoach.core.ids import SetCode

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"
FDN = SetCode("FDN")


def test_the_registry_is_empty_until_the_effect_model_exists() -> None:
    """M1 has no effect model, so claiming support for anything would be a lie."""
    assert not SUPPORTED_KEYWORDS


def test_an_empty_set_audits_cleanly() -> None:
    report = audit(FDN, [])
    assert report.card_count == 0
    assert report.unsupported == ()
    assert report.fully_supported
    assert report.affected_fraction == 0.0


def test_the_fixture_reports_its_real_mechanics() -> None:
    report = audit(FDN, cards_from_json_array(FIXTURE))
    assert report.set_code == FDN
    assert report.card_count == 8
    assert "Flying" in report.unsupported
    assert "Landfall" in report.unsupported
    assert not report.fully_supported


def test_keyword_counts_are_per_card_not_per_use() -> None:
    report = audit(FDN, cards_from_json_array(FIXTURE))
    assert report.keyword_counts["Flying"] == 1
    assert report.keyword_counts["Vigilance"] == 1


def test_unsupported_is_sorted_for_a_stable_report() -> None:
    report = audit(FDN, cards_from_json_array(FIXTURE))
    assert list(report.unsupported) == sorted(report.unsupported)


def test_only_cards_with_unmodelled_keywords_count_as_affected() -> None:
    """Four of the eight fixture cards are vanilla; they cost nothing to support."""
    report = audit(FDN, cards_from_json_array(FIXTURE))
    assert report.affected_cards == 4
    assert report.affected_fraction == 0.5


def test_supporting_a_keyword_shrinks_the_report() -> None:
    """The point of the parameter: cost a plan before committing to it."""
    cards = list(cards_from_json_array(FIXTURE))
    before = audit(FDN, cards)
    after = audit(FDN, cards, supported=frozenset({"Flying", "Vigilance", "Haste"}))
    assert "Flying" not in after.unsupported
    assert len(after.unsupported) < len(before.unsupported)
    assert after.affected_cards < before.affected_cards


def test_full_support_is_reported_as_such() -> None:
    cards = list(cards_from_json_array(FIXTURE))
    everything = frozenset({k for c in cards for k in c.keywords})
    report = audit(FDN, cards, supported=everything)
    assert report.fully_supported
    assert report.affected_cards == 0
