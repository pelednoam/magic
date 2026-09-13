"""Parsing mana costs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import cast

import pytest

from mtgcoach.core.ids import InstanceId
from mtgcoach.core.manacost import ManaCost, ManaSource, UnsupportedCostError, parse

FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "scryfall_fdn_sample.json"


def test_an_empty_cost() -> None:
    """A land costs nothing, which is not the same as costing zero generic."""
    cost = parse("")
    assert cost.is_free
    assert cost.total == 0


def test_generic_symbols_are_counted() -> None:
    assert parse("{2}{1}").generic == 3


def test_coloured_symbols_become_one_element_sets() -> None:
    cost = parse("{G}{G}")
    assert cost.symbols == (frozenset({"G"}), frozenset({"G"}))
    assert cost.colors == {"G"}


def test_a_real_cost_from_the_box() -> None:
    """Aurelia, the Warleader."""
    cost = parse("{2}{R}{R}{W}{W}")
    assert cost.generic == 2
    assert cost.total == 6
    assert cost.colors == {"R", "W"}


def test_hybrid_is_a_set_of_two_colours() -> None:
    """The box has none, but set #2 will -- and it needs no new solver code."""
    assert parse("{W/U}").symbols == (frozenset({"W", "U"}),)


def test_x_is_counted_but_not_charged() -> None:
    """CR 202.3b: X is zero everywhere except on the stack."""
    cost = parse("{X}{G}")
    assert cost.variable == 1
    assert cost.total == 1


def test_colorless_is_distinct_from_generic() -> None:
    """{C} needs specifically colourless mana; {1} takes anything."""
    cost = parse("{C}{1}")
    assert cost.colorless == 1
    assert cost.generic == 1


def test_lower_case_is_accepted() -> None:
    assert parse("{2}{g}") == parse("{2}{G}")


@pytest.mark.parametrize("bad", ["{2/W}", "{G/P}", "{Q}", "{W/U/B}"])
def test_costs_the_solver_cannot_model_are_rejected(bad: str) -> None:
    """Rejected rather than approximated.

    A mis-modelled cost is a coach saying you can cast something you cannot.
    """
    with pytest.raises(UnsupportedCostError):
        parse(bad)


@pytest.mark.parametrize("bad", ["two green", "{G} and more", "GG"])
def test_anything_that_is_not_symbols_is_rejected(bad: str) -> None:
    with pytest.raises(UnsupportedCostError, match="is not a mana cost"):
        parse(bad)


def test_an_empty_cost_has_no_colours() -> None:
    assert ManaCost().colors == frozenset()


def test_a_source_pays_a_symbol_it_shares_a_colour_with() -> None:
    forest = ManaSource(InstanceId("forest"), frozenset({"G"}))
    assert forest.can_pay(frozenset({"G"}))
    assert not forest.can_pay(frozenset({"U"}))
    assert forest.can_pay(frozenset({"G", "U"})), "a hybrid symbol"


def test_a_colourless_source_pays_no_coloured_symbol() -> None:
    assert not ManaSource(InstanceId("wastes")).can_pay(frozenset({"G"}))


def test_every_cost_in_the_scryfall_fixture_parses() -> None:
    """Real Scryfall strings, not ones written to suit the parser.

    The whole Beginner Box was checked at extraction time, but no committed
    fixture carries mana costs -- ``effects.json`` holds abilities and the
    decklists hold names -- so this pins the parser against the only real
    costs the repository actually stores.
    """
    costs = _face_costs(json.loads(FIXTURE.read_text(encoding="utf-8")))
    assert costs, "the fixture should carry some costs"
    for text in costs:
        assert parse(text).total >= 0


def test_a_two_faced_cards_joined_cost_is_refused() -> None:
    """Scryfall joins them at the top level; resolving to one half would lie."""
    joined = [
        c["mana_cost"]
        for c in json.loads(FIXTURE.read_text(encoding="utf-8"))
        if isinstance(c.get("mana_cost"), str) and "//" in c["mana_cost"]
    ]
    assert joined, "the fixture should carry a split card"
    for text in joined:
        with pytest.raises(UnsupportedCostError, match="not a mana cost"):
            parse(text)


def _face_costs(cards: list[dict[str, object]]) -> list[str]:
    """Every per-face mana cost in a Scryfall payload.

    A card with faces carries the real costs there; its top-level ``mana_cost``
    is the two joined with ``//``.
    """
    found: list[str] = []
    for card in cards:
        faces: object = card.get("card_faces")
        if isinstance(faces, list):
            nested: list[dict[str, object]] = [
                f for f in cast("list[object]", faces) if isinstance(f, dict)
            ]
            found.extend(_face_costs(nested))
            continue
        cost = card.get("mana_cost")
        if isinstance(cost, str) and cost:
            found.append(cost)
    return found
