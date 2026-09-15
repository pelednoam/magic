"""What you may do, and why not."""

from __future__ import annotations

from dataclasses import replace

from helpers import ME, YOU, deck, facts
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import CastSpell
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
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step

FOREST = ManaSource(InstanceId("forest"), frozenset("G"))
ISLAND = ManaSource(InstanceId("island"), frozenset("U"))


def forests(count: int) -> list[ManaSource]:
    """``count`` *distinct* Forests.

    Passing one ManaSource several times is a caller bug the solver now refuses:
    a single permanent cannot be tapped twice, and letting it silently pay twice
    over would offer a spell that cannot actually be cast.
    """
    return [ManaSource(InstanceId(f"forest-{i}"), frozenset("G")) for i in range(count)]


def islands(count: int) -> list[ManaSource]:
    """``count`` distinct Islands."""
    return [ManaSource(InstanceId(f"island-{i}"), frozenset("U")) for i in range(count)]


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
    reasons = why_not_cast(_game(Step.DECLARE_ATTACKERS), ME, AURELIA, forests(6))
    assert "you can only play this in a main phase" in reasons


def test_a_creature_cannot_be_cast_on_the_opponents_turn() -> None:
    reasons = why_not_cast(_game(Step.PRECOMBAT_MAIN, YOU), ME, AURELIA, forests(6))
    assert "you can only play this on your own turn" in reasons


def test_being_short_of_mana_says_how_short() -> None:
    """'You need 5 more' teaches; 'you cannot cast that' does not."""
    reasons = why_not_cast(_game(), ME, AURELIA, [FOREST])
    assert "you need 5 more untapped sources" in reasons


def test_one_short_is_singular() -> None:
    cheap = facts("Bear", "{1}{G}", creature=True, power=2, toughness=2)
    assert "you need 1 more untapped source" in why_not_cast(_game(), ME, cheap, [FOREST])


def test_having_no_source_of_a_colour_says_which() -> None:
    reasons = why_not_cast(_game(), ME, CANCEL, forests(3))
    assert "you have no source of U" in reasons


def test_enough_sources_but_the_wrong_combination() -> None:
    """Two Islands cannot pay {G}{G} even though the count is right."""
    both = facts("Hybrid", "{G}{G}")
    reasons = why_not_cast(_game(), ME, both, islands(2))
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


def _waiting(state: GameState, caster: PlayerId) -> GameState:
    """The same board with one spell on the stack, cast by ``caster``."""
    return apply(state, CastSpell(caster, state.player(caster).hand[0].instance_id))


def test_a_spell_waiting_to_resolve_stops_sorcery_speed() -> None:
    """The third half of CR 117.1a, which had no stack to look at until now.

    A spell waiting to resolve means it is not your turn to act at sorcery
    speed, however much it looks like your main phase.
    """
    main = _game()
    # A creature a single Forest pays for, so nothing but the stack is in the
    # way and the difference between the two calls is only the waiting spell.
    bear = facts("Bear", "{G}", creature=True, power=1, toughness=1)
    assert can_cast(main, ME, bear, [FOREST])
    reasons = why_not_cast(_waiting(main, ME), ME, bear, [FOREST])
    assert reasons == ("you can only play this when nothing is waiting to resolve",)


def test_the_opponents_spell_stops_it_too() -> None:
    """Sorcery timing asks whether *the* stack is empty, not whether yours is.

    The stack is one zone in the rules (CR 405.1) and is filed per-owner here,
    so a check that looked only at your own half would let you cast a creature
    in response to theirs -- which is the one thing sorcery speed forbids.
    """
    bear = facts("Bear", "{G}", creature=True, power=1, toughness=1)
    reasons = why_not_cast(_waiting(_game(), YOU), ME, bear, [FOREST])
    assert reasons == ("you can only play this when nothing is waiting to resolve",)


def test_an_instant_is_unaffected_by_a_waiting_spell() -> None:
    """Which is what instant speed *is*: answering something on the stack."""
    assert can_cast(_waiting(_game(), YOU), ME, GIANT_GROWTH, [FOREST])
