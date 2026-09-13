"""What you may do, and why not."""

from __future__ import annotations

from dataclasses import replace

from helpers import ME, YOU, deck, facts
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.legality import (
    can_attack,
    can_cast,
    can_play_land,
    why_not_attack,
    why_not_cast,
    why_not_play_land,
)
from mtgcoach.core.manacost import ManaSource
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step

FOREST = ManaSource("forest", frozenset("G"))
ISLAND = ManaSource("island", frozenset("U"))

GIANT_GROWTH = facts("Giant Growth", "{G}", instant=True)
AURELIA = facts("Aurelia", "{2}{R}{R}{W}{W}", creature=True, power=3, toughness=4)
CANCEL = facts("Cancel", "{1}{U}{U}", instant=True)
PLAINS = facts("Plains", land=True)


def _game(step: Step = Step.PRECOMBAT_MAIN, active: PlayerId = ME) -> GameState:
    game = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    return replace(game, step=step, active_player=active)


# --- casting ---------------------------------------------------------------


def test_an_instant_can_be_cast_in_combat() -> None:
    assert can_cast(_game(Step.DECLARE_BLOCKERS), ME, GIANT_GROWTH, [FOREST])


def test_an_instant_can_be_cast_on_the_opponents_turn() -> None:
    assert can_cast(_game(Step.UPKEEP, YOU), ME, GIANT_GROWTH, [FOREST])


def test_a_creature_cannot_be_cast_in_combat() -> None:
    reasons = why_not_cast(_game(Step.DECLARE_ATTACKERS), ME, AURELIA, [FOREST] * 6)
    assert "you can only play this in a main phase" in reasons


def test_a_creature_cannot_be_cast_on_the_opponents_turn() -> None:
    reasons = why_not_cast(_game(Step.PRECOMBAT_MAIN, YOU), ME, AURELIA, [FOREST] * 6)
    assert "you can only play this on your own turn" in reasons


def test_being_short_of_mana_says_how_short() -> None:
    """'You need 5 more' teaches; 'you cannot cast that' does not."""
    reasons = why_not_cast(_game(), ME, AURELIA, [FOREST])
    assert "you need 5 more untapped sources" in reasons


def test_one_short_is_singular() -> None:
    cheap = facts("Bear", "{1}{G}", creature=True, power=2, toughness=2)
    assert "you need 1 more untapped source" in why_not_cast(_game(), ME, cheap, [FOREST])


def test_having_no_source_of_a_colour_says_which() -> None:
    reasons = why_not_cast(_game(), ME, CANCEL, [FOREST, FOREST, FOREST])
    assert "you have no source of U" in reasons


def test_enough_sources_but_the_wrong_combination() -> None:
    """Two Islands cannot pay {G}{G} even though the count is right."""
    both = facts("Hybrid", "{G}{G}")
    reasons = why_not_cast(_game(), ME, both, [ISLAND, ISLAND])
    assert "no source of G" in reasons[0]


def test_a_land_cannot_be_cast() -> None:
    assert "lands are played, not cast" in why_not_cast(_game(), ME, PLAINS, [])


# --- playing lands ---------------------------------------------------------


def test_a_land_can_be_played_in_a_main_phase() -> None:
    assert can_play_land(_game(), ME, PLAINS)


def test_only_one_land_a_turn() -> None:
    game = _game()
    spent = replace(game.player(ME), lands_played_this_turn=1)
    reasons = why_not_play_land(game.with_player(ME, spent), ME, PLAINS)
    assert "you have already played a land this turn" in reasons


def test_a_land_cannot_be_played_in_combat() -> None:
    assert "in a main phase" in why_not_play_land(_game(Step.COMBAT_DAMAGE), ME, PLAINS)[0]


def test_a_nonland_is_not_a_land() -> None:
    assert "Giant Growth is not a land" in why_not_play_land(_game(), ME, GIANT_GROWTH)


# --- attacking -------------------------------------------------------------


def _permanent(name: str, *, tapped: bool = False, sick: bool = True) -> Permanent:
    perm = Permanent(CardInstance(InstanceId(name), OracleId(name)), tapped=tapped)
    return perm if sick else perm.settle()


def test_a_settled_untapped_creature_can_attack() -> None:
    bear = facts("Bear", creature=True, power=2, toughness=2)
    assert can_attack(_permanent("Bear", sick=False), bear)


def test_a_tapped_creature_cannot_attack() -> None:
    bear = facts("Bear", creature=True, power=2, toughness=2)
    reasons = why_not_attack(_permanent("Bear", tapped=True, sick=False), bear)
    assert "Bear is tapped" in reasons


def test_summoning_sickness_stops_an_attack() -> None:
    bear = facts("Bear", creature=True, power=2, toughness=2)
    reasons = why_not_attack(_permanent("Bear"), bear)
    assert any("since your turn began" in r for r in reasons)


def test_haste_beats_summoning_sickness() -> None:
    hasty = facts("Goblin", "", "Haste", creature=True, power=1, toughness=1)
    assert can_attack(_permanent("Goblin"), hasty)


def test_defender_cannot_attack() -> None:
    wall = facts("Wall", "", "Defender", creature=True, power=0, toughness=4)
    assert "Wall has defender" in why_not_attack(_permanent("Wall", sick=False), wall)


def test_a_noncreature_cannot_attack() -> None:
    assert "is not a creature" in why_not_attack(_permanent("Plains", sick=False), PLAINS)[0]


def test_the_right_number_of_sources_in_the_wrong_colours() -> None:
    """A Plains and an Island is two mana, and still not {W}{W}.

    Neither of the cheaper explanations fits: nothing is short, and there *is* a
    white source. Saying so beats saying "you can't cast that".
    """
    card = facts("Blessed Hippogriff", "{W}{W}")
    plains = ManaSource("plains", frozenset("W"))
    (reason,) = why_not_cast(_game(), ME, card, [plains, ISLAND])
    assert "combination of colours" in reason
