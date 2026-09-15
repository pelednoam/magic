"""Who may act, and what happens when nobody wants to.

The rules in ``priority`` read as small functions, and each one is a sentence
of CR 117 that the engine had no way to say before. The reducer tests exercise
them through events; these ask them directly, because two of the answers are
about states an event cannot reach.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from helpers import ME, YOU, at_step, deck
from mtgcoach.core import priority
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import CastSpell
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState


def test_turn_order_starts_with_the_active_player() -> None:
    """CR 101.4. Priority travels in this order, so it has to be this order."""
    game = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    assert priority.turn_order(game) == (ME, YOU)
    assert priority.turn_order(replace(game, active_player=YOU)) == (YOU, ME)


def test_who_still_has_to_pass_starts_from_the_holder(main: GameState) -> None:
    """In the order they act, which is the order a screen has to show them in."""
    assert priority.yet_to_pass(main) == (ME, YOU)
    one = priority.passes(main, ME)
    assert priority.yet_to_pass(one) == (YOU,)
    assert priority.yet_to_pass(priority.passes(one, YOU)) == ()


def test_nobody_has_to_pass_in_a_step_that_hands_out_no_priority(game: GameState) -> None:
    """CR 502.4, and why the harness can end an untap step with one event."""
    assert game.step is Step.UNTAP
    assert priority.yet_to_pass(game) == ()


def test_the_nonactive_player_passing_first_hands_it_back(main: GameState) -> None:
    """Priority does not have to start with the active player to travel right.

    It starts with them at the beginning of a step (CR 117.3a), but a spell
    changes that: the caster keeps it (CR 117.3c) and it goes to the *next*
    player from there (CR 117.3d). A version of ``yet_to_pass`` that always
    began at the active player would have asked the wrong seat to pass.
    """
    theirs = replace(main, priority=YOU, passed=())
    assert priority.yet_to_pass(theirs) == (YOU, ME)
    assert priority.passes(theirs, YOU).priority == ME


def test_an_action_clears_the_passes(main: GameState) -> None:
    """CR 117.4's "in succession", which is the word doing the work.

    Pass, then cast: the earlier pass no longer counts. Without that, one more
    pass from the opponent would resolve a spell that had been cast *after*
    they passed -- so they would never have had the chance to answer it.
    """
    passed = priority.passes(main, ME)
    assert passed.passed == (ME,)
    card = passed.player(YOU).hand[0]
    after = apply(passed, CastSpell(YOU, card.instance_id))
    assert after.passed == ()
    assert after.priority == YOU
    assert not priority.all_passed(after)


def test_a_board_where_nobody_holds_priority_says_so_plainly(main: GameState) -> None:
    """A state no played game reaches, and the honest answer for it.

    ``priority`` defaults to None because a game begins in the untap step,
    where that is right -- so a board assembled by hand at a main phase has
    nobody able to act and nobody having passed. It must not be described as
    "every player has passed": that is a different position, with a spell about
    to resolve, and saying it would be the engine misstating its own rules.
    ``selfplay.watching`` reports such a board as broken.
    """
    stuck = replace(main, priority=None, passed=())
    assert priority.lacking(stuck, ME) == ("nobody has priority right now",)
    with pytest.raises(IllegalEventError, match="nobody has priority right now"):
        priority.demanded(stuck, ME)


def test_every_player_having_passed_says_what_it_is_waiting_for(main: GameState) -> None:
    """Two different positions, and a player needs to know which (CR 117.4)."""
    empty = priority.passes(priority.passes(main, ME), YOU)
    assert priority.lacking(empty, ME) == (
        "every player has passed, so nothing happens until the step ends",
    )
    card = main.player(ME).hand[0]
    on_stack = apply(main, CastSpell(ME, card.instance_id))
    waiting = priority.passes(priority.passes(on_stack, ME), YOU)
    assert priority.lacking(waiting, ME) == (
        "every player has passed, so nothing happens until the top of the stack resolves",
    )


def test_a_step_that_hands_out_none_says_that_instead(game: GameState) -> None:
    """CR 502.4 is a more useful sentence than "somebody else has it".

    There is nothing to wait for in the untap step, so "you do not have
    priority right now" would leave a player looking for a pass that is never
    coming.
    """
    assert priority.lacking(game, ME) == ("nobody gets priority during the untap step",)


def test_the_holder_is_lacking_nothing(main: GameState) -> None:
    assert priority.lacking(main, ME) == ()


def test_entering_a_step_hands_priority_to_the_active_player(game: GameState) -> None:
    """CR 117.3a, and nobody at all in the two steps that have none."""
    assert priority.begins(game).priority is None
    assert at_step(game, Step.UPKEEP).priority == ME
    assert at_step(game, Step.CLEANUP).priority is None
    assert at_step(game, Step.DECLARE_ATTACKERS, YOU).priority == YOU
