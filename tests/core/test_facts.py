"""The narrow view the engine takes of a card."""

from __future__ import annotations

from helpers import facts


def test_a_keyword_matches_whatever_case_it_was_printed_in() -> None:
    """Scryfall prints 'First strike'; the engine asks for whatever reads best."""
    card = facts("Boros Recruit", "{R/W}", "First strike")
    assert card.has("First strike")
    assert card.has("first strike")
    assert card.has("FIRST STRIKE")


def test_a_keyword_it_does_not_have() -> None:
    assert not facts("Grizzly Bears", "{1}{G}").has("Flying")


def test_a_card_with_no_keywords_has_none() -> None:
    assert facts("Plains", land=True).keywords == frozenset()


def test_power_and_toughness_are_absent_rather_than_zero() -> None:
    """A ``*`` power is unknown, and every consumer has to say what it does."""
    star = facts("Consuming Aberration", "{3}{U}{B}", creature=True)
    assert star.power is None
    assert star.toughness is None


def test_a_creature_carries_its_printed_stats() -> None:
    bear = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
    assert (bear.power, bear.toughness) == (2, 2)
    assert bear.is_creature
    assert not bear.is_land
