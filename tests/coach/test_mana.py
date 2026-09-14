"""What mana the board could make right now."""

from __future__ import annotations

from helpers_coach import Book, land, on_battlefield, taps_for

from helpers import facts
from mtgcoach.coach.mana import available, colours_in
from mtgcoach.core.abilities import ActivatedAbility, UnmodeledAbility
from mtgcoach.core.effects import Draw, ProduceMana
from mtgcoach.core.targets import Controller
from mtgcoach.core.vocabulary import AbilityCost

FOREST, FOREST_RULES = land("Forest", "{G}")
ISLAND, ISLAND_RULES = land("Island", "{U}")
BOOK = Book(
    cards={"Forest": FOREST, "Island": ISLAND},
    rules={"Forest": FOREST_RULES, "Island": ISLAND_RULES},
)


def test_an_untapped_forest_is_a_green_source() -> None:
    (source,) = available([on_battlefield("Forest")], BOOK)
    assert source.produces == frozenset("G")


def test_a_tapped_land_makes_nothing() -> None:
    assert available([on_battlefield("Forest", tapped=True)], BOOK) == ()


def test_two_lands_are_two_sources_with_distinct_identities() -> None:
    """The solver keys payments by identity; one Forest cannot pay twice."""
    board = [on_battlefield("Forest", "1"), on_battlefield("Forest", "2")]
    sources = available(board, BOOK)
    assert len({s.instance_id for s in sources}) == 2


def test_a_card_the_book_does_not_know_is_skipped() -> None:
    assert available([on_battlefield("Mystery")], BOOK) == ()


def test_a_permanent_with_no_mana_ability_is_not_a_source() -> None:
    book = Book(cards={"Bear": facts("Bear", creature=True)}, rules={"Bear": ()})
    assert available([on_battlefield("Bear")], book) == ()


def test_a_summoning_sick_creature_cannot_tap_for_mana() -> None:
    """CR 302.6. Llanowar Elves does nothing the turn you play it."""
    elves = facts("Llanowar Elves", "{G}", power=1, toughness=1, creature=True)
    book = Book(cards={"Llanowar Elves": elves}, rules={"Llanowar Elves": (taps_for("{G}"),)})
    assert available([on_battlefield("Llanowar Elves", sick=True)], book) == ()
    assert available([on_battlefield("Llanowar Elves")], book) != ()


def test_a_summoning_sick_land_is_still_a_source() -> None:
    """Sickness stops a {T} cost only on creatures; a land played now taps fine."""
    assert available([on_battlefield("Forest", sick=True)], BOOK) != ()


def test_a_dual_land_makes_both_colours() -> None:
    dual = facts("Tundra", land=True)
    book = Book(cards={"Tundra": dual}, rules={"Tundra": (taps_for("{W}"), taps_for("{U}"))})
    (source,) = available([on_battlefield("Tundra")], book)
    assert source.produces == frozenset("WU")


def test_a_source_of_colourless_mana_has_an_empty_colour_set() -> None:
    """Empty is not "no source": it pays generic costs and {C}."""
    wastes = facts("Wastes", land=True)
    book = Book(cards={"Wastes": wastes}, rules={"Wastes": (taps_for("{C}"),)})
    (source,) = available([on_battlefield("Wastes")], book)
    assert source.produces == frozenset()


def test_an_ability_that_costs_mana_is_not_a_source() -> None:
    """It would be paid out of the pool the solver is trying to fill."""
    filtered = ActivatedAbility(AbilityCost(mana="{1}", tap=True), (ProduceMana("{W}{U}"),))
    book = Book(cards={"Filter": facts("Filter", land=True)}, rules={"Filter": (filtered,)})
    assert available([on_battlefield("Filter")], book) == ()


def test_an_ability_that_sacrifices_itself_is_not_a_source() -> None:
    ritual = ActivatedAbility(AbilityCost(sacrifice_self=True), (ProduceMana("{B}"),))
    book = Book(cards={"Lotus": facts("Lotus")}, rules={"Lotus": (ritual,)})
    assert available([on_battlefield("Lotus")], book) == ()


def test_an_ability_that_does_something_else_is_not_a_mana_ability() -> None:
    """CR 605.1a: it makes mana and nothing else, or it uses the stack."""
    mixed = ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"), Draw(1, Controller.YOU)))
    book = Book(cards={"Odd": facts("Odd", land=True)}, rules={"Odd": (mixed,)})
    assert available([on_battlefield("Odd")], book) == ()


def test_an_unmodelled_ability_is_not_a_source() -> None:
    puzzle = UnmodeledAbility("Add one mana of any colour", "any-colour is not modelled")
    book = Book(cards={"Puzzle": facts("Puzzle", land=True)}, rules={"Puzzle": (puzzle,)})
    assert available([on_battlefield("Puzzle")], book) == ()


def test_colours_are_read_out_of_the_produced_string() -> None:
    assert colours_in("{G}") == frozenset("G")
    assert colours_in("{W}{U}") == frozenset("WU")
    assert colours_in("{C}") == frozenset()
    assert colours_in("") == frozenset()
