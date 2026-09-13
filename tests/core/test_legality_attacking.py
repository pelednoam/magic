"""When an attack can be declared, and by which creature.

Two questions, deliberately separate. One is about the clock and is asked once;
the other is about a creature and is asked once per creature. A caller that
asked only the second was told a tapped creature could attack at the upkeep.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from helpers import ME, YOU, deck, facts
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.legality import (
    can_attack,
    can_cast,
    can_declare_attackers,
    why_not_cast,
    why_not_declare_attackers,
)
from mtgcoach.core.manacost import ManaSource
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step

FOREST = ManaSource(InstanceId("forest"), frozenset("G"))
GIANT_GROWTH = facts("Giant Growth", "{G}", instant=True)


def _game(step: Step = Step.PRECOMBAT_MAIN, active: PlayerId = ME) -> GameState:
    game = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    return replace(game, step=step, active_player=active)


def test_an_attack_can_be_declared_in_your_declare_attackers_step() -> None:
    assert can_declare_attackers(_game(Step.DECLARE_ATTACKERS), ME)


def test_no_attack_on_the_opponents_turn() -> None:
    state = _game(Step.DECLARE_ATTACKERS, YOU)
    (reason,) = why_not_declare_attackers(state, ME)
    assert "your own turn" in reason


def test_no_attack_outside_the_declare_attackers_step() -> None:
    """A creature that *could* attack still cannot attack at the upkeep."""
    bear = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
    ready = Permanent(CardInstance(InstanceId("b"), OracleId("b"))).settle()
    assert can_attack(ready, bear), "the creature itself is able"
    (reason,) = why_not_declare_attackers(_game(Step.UPKEEP), ME)
    assert "declare attackers step" in reason


def test_a_card_with_no_mana_cost_cannot_be_cast() -> None:
    """CR 202.1a. Not the same as costing {0}, which both used to parse as."""
    costless = facts("Ancestral Vision", "", instant=True)
    reasons = why_not_cast(_game(), ME, costless, [])
    assert any("no mana cost" in r for r in reasons)


def test_a_zero_cost_spell_can_be_cast() -> None:
    assert can_cast(_game(), ME, facts("Free Spell", "{0}"), [])


def test_an_unknown_player_is_an_error_even_for_an_instant() -> None:
    """An instant skipped every state lookup, so a bad id read as castable."""
    with pytest.raises(IllegalEventError, match="no such player"):
        why_not_cast(_game(), PlayerId("nobody"), GIANT_GROWTH, [FOREST])
