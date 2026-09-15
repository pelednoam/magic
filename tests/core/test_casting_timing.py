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

from helpers import ME, YOU, all_pass
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.events import AdvanceStep, CastSpell, PassPriority, ResolveSpell, SetTapped
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.reduce import apply
from mtgcoach.core.steps import Step
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState


def cast(state: GameState, player: PlayerId = ME) -> tuple[GameState, CardInstance]:
    """Put the first card in a player's hand on the stack.

    Its own copy rather than imported from ``test_casting``: a test module
    importing a sibling test module works under pytest and not under mypy,
    which is a seam not worth having for four lines.
    """
    card = state.player(player).hand[0]
    return apply(state, CastSpell(player, card.instance_id)), card


def test_the_step_cannot_end_while_a_spell_is_waiting(main: GameState) -> None:
    """CR 500.2, and the first version of this test had it backwards.

    It asserted that a cast spell was still on the stack a step later, on the
    reasoning that "a spell resolves because somebody let it, not because time
    passed". The first half is right and the conclusion is wrong: a step *ends*
    when the stack is empty and all players pass, so the game cannot walk away
    from a spell it has not resolved. A test that pinned the old behaviour was
    pinning a rule the game does not have.
    """
    on_stack, card = cast(main)
    with pytest.raises(IllegalEventError, match="waiting to resolve"):
        apply(all_pass(on_stack), AdvanceStep())
    resolved = apply(all_pass(on_stack), ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))
    assert apply(all_pass(resolved), AdvanceStep()).step is Step.BEGIN_COMBAT


def test_the_step_cannot_end_until_both_players_have_passed(main: GameState) -> None:
    """The other half of CR 500.2, which had nothing to check it with.

    "Simply having the stack become empty doesn't cause such a phase or step to
    end; all players have to pass in succession with the stack empty. Because
    of this, each player gets a chance to add new things to the stack before
    that phase or step ends." The engine used to accept ``AdvanceStep`` on an
    empty stack from anybody at any time, so a client could walk straight past
    the other player's only chance to answer.
    """
    with pytest.raises(IllegalEventError, match="does not end until me, you passes"):
        apply(main, AdvanceStep())
    one = apply(main, PassPriority(ME))
    with pytest.raises(IllegalEventError, match="does not end until you passes"):
        apply(one, AdvanceStep())
    assert apply(all_pass(main), AdvanceStep()).step is Step.BEGIN_COMBAT


def test_a_spell_the_opponent_cast_stops_the_step_too(main: GameState) -> None:
    """The stack is one zone, and one field."""
    theirs, _ = cast(apply(main, PassPriority(ME)), YOU)
    with pytest.raises(IllegalEventError, match="waiting to resolve"):
        apply(all_pass(theirs), AdvanceStep())


def test_only_the_top_of_the_stack_resolves(main: GameState) -> None:
    """CR 405.5 and CR 608.1: the *last* object added is the one that resolves.

    Two spells at once used to be something nothing could produce, so this was
    a rule held in advance -- and it was held over one player's half of a stack
    that had two halves and no order between them. Now it is the real rule over
    the real stack, and the next test is the one it was waiting for.
    """
    first, early = cast(main)
    later_card = first.player(ME).hand[0]
    both = apply(first, CastSpell(ME, later_card.instance_id))
    passed = all_pass(both)
    with pytest.raises(IllegalEventError, match="not the top"):
        apply(passed, ResolveSpell(ME, early.instance_id, ZoneName.GRAVEYARD))
    assert apply(passed, ResolveSpell(ME, later_card.instance_id, ZoneName.GRAVEYARD)) is not None


def test_a_spell_cast_in_answer_resolves_first(main: GameState) -> None:
    """CR 117.7, and the board the old per-player stack got wrong.

    I cast a creature; you answer it with a trick. Yours was put on the stack
    last, so yours resolves first (CR 405.2, CR 405.5). Two tuples filed under
    two players had no way to compare their order, so the engine let *mine*
    resolve first -- the exact opposite -- and the app happily asked it to.
    """
    mine, creature = cast(main)
    answered, trick = cast(apply(mine, PassPriority(ME)), YOU)
    passed = all_pass(answered)
    with pytest.raises(IllegalEventError, match="not the top"):
        apply(passed, ResolveSpell(ME, creature.instance_id, ZoneName.BATTLEFIELD))
    first = apply(passed, ResolveSpell(YOU, trick.instance_id, ZoneName.GRAVEYARD))
    assert [one.instance_id for one in first.stack] == [creature.instance_id]
    assert first.player(YOU).graveyard == (trick,)


def test_a_spell_does_not_resolve_until_everybody_has_passed(main: GameState) -> None:
    """CR 117.4 and CR 608.1, which is the whole of R04 in one assertion.

    A spell resolves because every player passed in succession -- not because
    its controller asked. The app asked, one event after casting, so the other
    player's window to answer closed before it opened.
    """
    on_stack, card = cast(main)
    with pytest.raises(IllegalEventError, match="does not resolve until me, you passes"):
        apply(on_stack, ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))
    half = apply(on_stack, PassPriority(ME))
    with pytest.raises(IllegalEventError, match="does not resolve until you passes"):
        apply(half, ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))
    assert apply(all_pass(on_stack), ResolveSpell(ME, card.instance_id, ZoneName.GRAVEYARD))


def test_a_cast_taps_what_pays_for_it(main: GameState) -> None:
    """One event, because CR 601.2 is one action.

    Sending the taps as separate events first was wrong about the rules and
    broken in practice: the server rechecks affordability when the cast
    arrives, and the mana it would have counted was already spent.
    """
    board = _with_lands(main, 2)
    card = board.player(ME).hand[0]
    sources = tuple(p.instance_id for p in board.player(ME).battlefield)
    after = apply(board, CastSpell(ME, card.instance_id, sources))
    assert all(p.tapped for p in after.player(ME).battlefield)
    assert [one.card for one in after.stack] == [card]


def test_a_refused_cast_taps_nothing(main: GameState) -> None:
    """All of the action or none of it.

    A player whose lands were tapped by a cast the server then refused would be
    worse off than one whose cast was simply refused.
    """
    board = _with_lands(main, 2)
    card = board.player(ME).hand[0]
    good = board.player(ME).battlefield[0].instance_id
    with pytest.raises(IllegalEventError, match="to pay with"):
        apply(board, CastSpell(ME, card.instance_id, (good, InstanceId("nobody"))))
    assert not any(p.tapped for p in board.player(ME).battlefield)


def test_a_tapped_land_cannot_pay(main: GameState) -> None:
    board = _with_lands(main, 1)
    land = board.player(ME).battlefield[0].instance_id
    tapped = apply(board, SetTapped(ME, land, tapped=True))
    card = tapped.player(ME).hand[0]
    with pytest.raises(IllegalEventError, match="already tapped"):
        apply(tapped, CastSpell(ME, card.instance_id, (land,)))


def test_the_same_land_cannot_pay_twice(main: GameState) -> None:
    """Which the tapped check catches: the second time round, it is tapped."""
    board = _with_lands(main, 1)
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
