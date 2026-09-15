"""Saying what is missing, not merely that something is.

"You can't cast that" teaches nothing. Each of these is a different sentence a
beginner needs, and each was once the wrong one.
"""

from __future__ import annotations

from helpers import ME, YOU, at_step, deck, facts
from mtgcoach.core.ids import InstanceId, PlayerId
from mtgcoach.core.legality import can_cast, why_not_cast
from mtgcoach.core.manacost import ManaSource
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step

FOREST = ManaSource(InstanceId("forest"), frozenset("G"))
ISLAND = ManaSource(InstanceId("island"), frozenset("U"))
PLAINS = ManaSource(InstanceId("plains"), frozenset("W"))

GIANT_GROWTH = facts("Giant Growth", "{G}", instant=True)
CANCEL = facts("Cancel", "{1}{U}{U}", instant=True)


def forests(count: int) -> list[ManaSource]:
    """``count`` *distinct* Forests; one permanent cannot be tapped twice."""
    return [ManaSource(InstanceId(f"forest-{i}"), frozenset("G")) for i in range(count)]


def islands(count: int) -> list[ManaSource]:
    """``count`` distinct Islands."""
    return [ManaSource(InstanceId(f"island-{i}"), frozenset("U")) for i in range(count)]


def _game(
    step: Step = Step.PRECOMBAT_MAIN, active: PlayerId = ME, holder: PlayerId | None = None
) -> GameState:
    """A board at one step, with priority handed out the way the step hands it.

    ``holder`` says otherwise. The active player gets priority first
    (CR 117.3a), so a test about casting an instant on the *opponent's* turn
    has to say that the opponent has already passed (CR 117.3d) -- which is
    the moment that actually happens at a table, and which this helper could
    not express while nothing recorded a holder at all.
    """
    game = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    return at_step(game, step, active, holder)


def test_the_right_number_of_sources_in_the_wrong_colours() -> None:
    """A Plains and an Island is two mana, and still not {W}{W}.

    Neither of the cheaper explanations fits: nothing is short, and there *is* a
    white source. Saying so beats saying "you can't cast that".
    """
    card = facts("Blessed Hippogriff", "{W}{W}")
    plains = ManaSource(InstanceId("plains"), frozenset("W"))
    (reason,) = why_not_cast(_game(), ME, card, [plains, ISLAND])
    assert "combination of colours" in reason


def test_nobody_can_cast_anything_during_untap() -> None:
    """CR 502.4. An instant that reads as castable here is wrong advice."""
    (reason,) = why_not_cast(_game(Step.UNTAP), ME, GIANT_GROWTH, [FOREST])
    assert "priority" in reason
    assert "untap step" in reason


def test_nobody_can_cast_anything_during_cleanup() -> None:
    (reason,) = why_not_cast(_game(Step.CLEANUP), ME, GIANT_GROWTH, [FOREST])
    assert "priority" in reason


def test_the_no_priority_steps_do_not_also_complain_about_sorcery_timing() -> None:
    """One reason, the true one: nobody may act, not 'it is not your main phase'."""
    reasons = why_not_cast(_game(Step.UNTAP), ME, CANCEL, islands(3))
    assert len(reasons) == 1


def test_a_hybrid_symbol_names_no_missing_colour() -> None:
    """{W/U} is payable by either, so neither is 'the colour you lack'."""
    card = facts("Hybrid Spell", "{W/U}{G}")
    plains = ManaSource(InstanceId("plains"), frozenset("W"))
    (reason,) = why_not_cast(_game(), ME, card, [plains])
    assert "you need 1 more untapped source" in reason


def test_a_hybrid_cost_is_payable_by_either_half() -> None:
    plains = ManaSource(InstanceId("plains"), frozenset("W"))
    assert can_cast(_game(), ME, facts("Hybrid Spell", "{W/U}"), [plains])


def test_a_colourless_pip_is_explained_as_such() -> None:
    """Blaming a colour combination for a {C} cost teaches the wrong rule."""
    card = facts("Colourless Spell", "{1}{C}")
    (reason,) = why_not_cast(_game(), ME, card, forests(2))
    assert "colourless mana" in reason
