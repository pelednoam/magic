"""When a spell may be cast, paid for, and let go -- as opposed to where it goes.

Split from ``test_casting`` at the line limit, and the seam is a real one: that
file is about the zones a spell passes through, this one is about the rules that
say a game cannot simply walk past one.

Two of these pin rules the first version of the tests had backwards, which is
worth saying out loud: a test that asserts the wrong behaviour is worse than no
test, because it makes the wrong behaviour deliberate.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest

from helpers import ME, YOU
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import AdvanceStep, CastSpell, ResolveSpell, SetTapped
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.reduce import apply
from mtgcoach.core.steps import Step
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState


def cast(state: GameState) -> tuple[GameState, CardInstance]:
    """Put the first card in ME's hand on the stack.

    Its own copy rather than imported from ``test_casting``: a test module
    importing a sibling test module works under pytest and not under mypy,
    which is a seam not worth having for four lines.
    """
    card = state.player(ME).hand[0]
    return apply(state, CastSpell(ME, card.instance_id)), card


def test_the_step_cannot_end_while_a_spell_is_waiting(game: GameState) -> None:
    """CR 500.2, and the first version of this test had it backwards.

    It asserted that a cast spell was still on the stack a step later, on the
    reasoning that "a spell resolves because somebody let it, not because time
    passed". The first half is right and the conclusion is wrong: a step *ends*
    when the stack is empty and all players pass, so the game cannot walk away
    from a spell it has not resolved. A test that pinned the old behaviour was
    pinning a rule the game does not have.
    """
    on_stack, card = cast(game)
    with pytest.raises(IllegalEventError, match="waiting to resolve"):
        apply(on_stack, AdvanceStep())
    resolved = apply(on_stack, ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))
    assert apply(resolved, AdvanceStep()).step is Step.UPKEEP


def test_a_spell_the_opponent_cast_stops_the_step_too(game: GameState) -> None:
    """The stack is one zone, however it is filed."""
    theirs = apply(game, CastSpell(YOU, game.player(YOU).hand[0].instance_id))
    with pytest.raises(IllegalEventError, match="waiting to resolve"):
        apply(theirs, AdvanceStep())


def test_only_the_top_of_the_stack_resolves(game: GameState) -> None:
    """CR 608.1, within as much of the order as this engine keeps.

    Two spells on one player's stack cannot happen yet -- that needs priority,
    which the engine does not have -- so this is a rule held in advance rather
    than one anything currently breaks. It is never wrong, and it is what stops
    a client resolving the bottom one.
    """
    first, early = cast(game)
    later_card = first.player(ME).hand[0]
    both = apply(first, CastSpell(ME, later_card.instance_id))
    with pytest.raises(IllegalEventError, match="not the top"):
        apply(both, ResolveSpell(ME, early.instance_id, ZoneName.GRAVEYARD))
    assert apply(both, ResolveSpell(ME, later_card.instance_id, ZoneName.GRAVEYARD)) is not None


def test_a_cast_taps_what_pays_for_it(game: GameState) -> None:
    """One event, because CR 601.2 is one action.

    Sending the taps as separate events first was wrong about the rules and
    broken in practice: the server rechecks affordability when the cast
    arrives, and the mana it would have counted was already spent.
    """
    board = _with_lands(game, 2)
    card = board.player(ME).hand[0]
    sources = tuple(p.instance_id for p in board.player(ME).battlefield)
    after = apply(board, CastSpell(ME, card.instance_id, sources))
    assert all(p.tapped for p in after.player(ME).battlefield)
    assert after.player(ME).stack == (card,)


def test_a_refused_cast_taps_nothing(game: GameState) -> None:
    """All of the action or none of it.

    A player whose lands were tapped by a cast the server then refused would be
    worse off than one whose cast was simply refused.
    """
    board = _with_lands(game, 2)
    card = board.player(ME).hand[0]
    good = board.player(ME).battlefield[0].instance_id
    with pytest.raises(IllegalEventError, match="to pay with"):
        apply(board, CastSpell(ME, card.instance_id, (good, InstanceId("nobody"))))
    assert not any(p.tapped for p in board.player(ME).battlefield)


def test_a_tapped_land_cannot_pay(game: GameState) -> None:
    board = _with_lands(game, 1)
    land = board.player(ME).battlefield[0].instance_id
    tapped = apply(board, SetTapped(ME, land, tapped=True))
    card = tapped.player(ME).hand[0]
    with pytest.raises(IllegalEventError, match="already tapped"):
        apply(tapped, CastSpell(ME, card.instance_id, (land,)))


def test_the_same_land_cannot_pay_twice(game: GameState) -> None:
    """Which the tapped check catches: the second time round, it is tapped."""
    board = _with_lands(game, 1)
    land = board.player(ME).battlefield[0].instance_id
    card = board.player(ME).hand[0]
    with pytest.raises(IllegalEventError, match="already tapped"):
        apply(board, CastSpell(ME, card.instance_id, (land, land)))


def _with_lands(state: GameState, count: int) -> GameState:
    """The same board with ``count`` untapped permanents for ME to tap."""
    mine = state.player(ME)
    lands = tuple(
        Permanent(CardInstance(InstanceId(f"land-{n}"), OracleId("Forest"))) for n in range(count)
    )
    return state.with_player(ME, replace(mine, battlefield=(*mine.battlefield, *lands)))
