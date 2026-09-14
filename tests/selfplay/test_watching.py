"""What must be true after every event, whatever anybody played.

The value of self-play is here rather than in the play: a policy that does not
understand Magic still puts the engine through states no fixture would think
of, and the way to notice is to check the things no play may ever break.
"""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest
from helpers_selfplay import THEM, YOU, game

from mtgcoach.core.steps import Step
from mtgcoach.selfplay.watching import broken


def test_a_transition_that_changes_nothing_is_fine() -> None:
    state = game()
    assert list(broken(state, state)) == []


def test_a_card_that_vanishes_is_caught() -> None:
    """The conservation invariant `PlayerState.cards` exists to make checkable."""
    state = game()
    fewer = state.with_player(YOU, replace(state.player(YOU), hand=state.player(YOU).hand[1:]))
    assert any("had" in wrong and "now has" in wrong for wrong in broken(state, fewer))


def test_a_card_that_appears_is_caught_too() -> None:
    """Both directions. A duplicated card is as wrong as a lost one."""
    state = game()
    player = state.player(YOU)
    more = state.with_player(YOU, replace(player, hand=(*player.hand, player.library[0])))
    assert list(broken(state, more))


def test_a_card_in_two_places_at_once_is_caught() -> None:
    """`InstanceId` exists so "the Mountain you tapped" is distinguishable."""
    state = game()
    player = state.player(YOU)
    doubled = state.with_player(
        YOU, replace(player, hand=(player.hand[0], *player.hand), library=player.library[1:])
    )
    assert any("two places" in wrong for wrong in broken(state, doubled))


def test_a_swapped_identity_is_caught_even_at_the_same_count() -> None:
    """The count is not enough on its own.

    A card replaced by a copy of another keeps the total the same, which is
    why the check compares identities rather than lengths.
    """
    state = game()
    player = state.player(YOU)
    swapped = state.with_player(
        YOU, replace(player, hand=(player.hand[0], *player.hand[2:], player.hand[0]))
    )
    assert any("lost track of" in wrong for wrong in broken(state, swapped))


@pytest.mark.parametrize("life", [-2000, 2000])
def test_a_life_total_that_has_run_away_is_caught(life: int) -> None:
    """Wide on purpose: this is about arithmetic, not about game balance."""
    state = game()
    silly = state.with_player(THEM, replace(state.player(THEM), life=life))
    assert any("life" in wrong for wrong in broken(state, silly))


def test_a_second_land_drop_in_one_turn_is_caught() -> None:
    """The reducer enforces it; this catches a path that went around it."""
    state = game()
    greedy = state.with_player(YOU, replace(state.player(YOU), lands_played_this_turn=2))
    assert any("lands this turn" in wrong for wrong in broken(state, greedy))


def test_a_turn_before_the_first_is_caught() -> None:
    state = game()
    assert any("turn 0" in wrong for wrong in broken(state, replace(state, turn=0)))


def test_a_step_that_is_not_a_step_is_caught() -> None:
    """`Step` is a StrEnum, so a string arrives where one belongs.

    The cast is the point: nothing in the engine can produce this, and the
    check exists for the day something outside it does.
    """
    state = game()
    nonsense = replace(state, step=cast("Step", "halftime"))
    assert any("not a step" in wrong for wrong in broken(state, nonsense))


def test_every_real_step_is_accepted() -> None:
    state = game()
    for step in Step:
        assert list(broken(state, replace(state, step=step))) == []
