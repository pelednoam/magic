"""Handing a real card to the rules engine.

Every ``CardFacts`` in the repository used to be built by ``tests/helpers.py``,
so the engine was correct about cards nothing could actually give it.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.enginefacts import UnmodellableCardError, facts_for
from mtgcoach.carddata.scryfall import cards_in
from mtgcoach.core.manacost import parse

if TYPE_CHECKING:
    from mtgcoach.carddata.cards import Card

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"


def _card(name: str) -> Card:
    for card in cards_in(FIXTURE):
        if card.name.startswith(name):
            return card
    msg = f"{name} is not in the fixture"
    raise AssertionError(msg)


def test_a_creature_arrives_with_its_stats() -> None:
    facts = facts_for(_card("Aurelia"))
    assert facts.is_creature
    assert not facts.is_land
    assert (facts.power, facts.toughness) == (3, 4)
    assert facts.has("Flying")


def test_a_land_is_a_land_and_costs_nothing() -> None:
    facts = facts_for(_card("Bloodfell Caves"))
    assert facts.is_land
    assert not facts.cost.printed


def test_an_instant_is_instant_speed() -> None:
    facts = facts_for(_card("Abrade"))
    assert facts.is_instant_speed
    assert facts.cost.total == 2


def test_a_star_power_arrives_as_unknown_rather_than_zero() -> None:
    """Consuming Aberration is */*; a silent zero makes it look harmless."""
    facts = facts_for(_card("Consuming Aberration"))
    assert facts.is_creature
    assert facts.power is None
    assert facts.toughness is None


def test_a_two_faced_card_is_read_per_face() -> None:
    """The top-level cost is the two joined, which would price neither spell."""
    card = _card("My Precious")
    assert card.is_multifaced
    front = facts_for(card)
    assert front.name == card.faces[0].name
    assert front.cost == parse(card.faces[0].mana_cost)


def test_the_back_face_can_be_asked_for() -> None:
    card = _card("My Precious")
    assert facts_for(card, 1).name == card.faces[1].name


def test_a_face_that_does_not_exist_is_refused() -> None:
    with pytest.raises(UnmodellableCardError, match="no face"):
        facts_for(_card("Abrade"), 9)


def test_the_oracle_id_travels_with_the_facts() -> None:
    card = _card("Abrade")
    assert facts_for(card).oracle_id == card.oracle_id


def test_every_card_in_the_fixture_can_be_given_to_the_engine() -> None:
    """The claim worth pinning: real data goes in without a special case."""
    for card in cards_in(FIXTURE):
        for index in range(len(card.faces)):
            assert facts_for(card, index).name


def test_a_cost_the_parser_refuses_is_refused_here_too() -> None:
    """A misprized spell is worse than a card the coach says it does not know."""
    card = _card("Abrade")
    face = replace(card.faces[0], mana_cost="{W/P}")
    unmodellable = replace(card, faces=(face,))
    with pytest.raises(UnmodellableCardError, match="Abrade"):
        facts_for(unmodellable)
