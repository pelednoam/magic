"""The checks the reducer cannot make about casting, made where the cards are.

``core`` holds no card data, so ``CastSpell`` checks only that the card is in
hand and ``ResolveSpell`` only that it is on the stack and going somewhere a
spell can go. Everything about *this card* is checked here.

The last one is the important one. ``ResolveSpell`` takes its destination from
the caller, so a client sending ``to: battlefield`` for an Opt would put an
instant among the lands for the rest of the game -- which is precisely the bug
casting was added to fix, arriving from the other side of the wire.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from helpers import ME, YOU, at_step, deck, facts
from helpers_coach import Book, taps_for
from mtgcoach.api.eventfields import BadEventError
from mtgcoach.api.guard import check
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.events import CastSpell, ResolveSpell
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.stack import StackObject
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step
from mtgcoach.core.zones import ZoneName

BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
OPT = facts("Opt", "{U}", instant=True)

BOOK = Book(
    cards={"Forest": facts("Forest", land=True), "Bear": BEAR, "Opt": OPT},
    rules={"Forest": (taps_for("{G}"),), "Bear": (), "Opt": ()},
)

#: Enough Forests to pay for a Bear.
LANDS = 2


def _board(*, hand: tuple[str, ...] = (), stack: tuple[str, ...] = (), lands: int = 0) -> GameState:
    """A main phase with the given cards where the test wants them.

    ``stack`` goes on ``GameState`` rather than into the player, because the
    stack is one shared ordered zone now (CR 405.1) -- and each object says who
    controls it (CR 405.4), which is what the guard reads to find the card.
    """
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    mine = replace(
        state.player(ME),
        hand=tuple(CardInstance(InstanceId(f"h{n}"), OracleId(o)) for n, o in enumerate(hand)),
        battlefield=tuple(
            Permanent(CardInstance(InstanceId(f"l{n}"), OracleId("Forest"))) for n in range(lands)
        ),
    )
    waiting = tuple(
        StackObject(CardInstance(InstanceId(f"s{n}"), OracleId(o)), ME) for n, o in enumerate(stack)
    )
    board = replace(state.with_player(ME, mine), stack=waiting)
    return at_step(board, Step.PRECOMBAT_MAIN, ME)


#: The two Forests `_board(lands=2)` puts down.
PAYS = (InstanceId("l0"), InstanceId("l1"))


def test_a_castable_spell_is_allowed() -> None:
    check(CastSpell(ME, InstanceId("h0"), PAYS), _board(hand=("Bear",), lands=LANDS), BOOK)


def test_a_cast_that_names_too_little_is_refused() -> None:
    """The check `why_not_cast` cannot make.

    It asks whether the cost is payable at all from this board. This asks
    whether it is paid by the permanents the caller actually named, which is
    what keeps a Grizzly Bears from being cast off a single Forest.
    """
    board = _board(hand=("Bear",), lands=LANDS)
    with pytest.raises(BadEventError, match="costs 2 mana, which tapping l0 does not pay"):
        check(CastSpell(ME, InstanceId("h0"), (InstanceId("l0"),)), board, BOOK)


def test_a_cast_that_names_nothing_is_refused() -> None:
    """Which is the same hole, at its widest: casting for free."""
    board = _board(hand=("Bear",), lands=LANDS)
    with pytest.raises(BadEventError, match="tapping nothing does not pay"):
        check(CastSpell(ME, InstanceId("h0")), board, BOOK)


def test_a_cast_that_names_something_that_makes_no_mana_is_refused() -> None:
    """A creature is a permanent and is not a Forest."""
    board = _board(hand=("Bear",), lands=LANDS)
    with pytest.raises(BadEventError, match="makes no mana"):
        check(CastSpell(ME, InstanceId("h0"), (InstanceId("h0"),)), board, BOOK)


def test_a_spell_you_cannot_pay_for_is_refused() -> None:
    """In the coach's own words, because it is the coach's own check."""
    with pytest.raises(BadEventError, match="Grizzly Bears: you need"):
        check(CastSpell(ME, InstanceId("h0")), _board(hand=("Bear",)), BOOK)


def test_a_sorcery_speed_spell_on_the_wrong_turn_is_refused() -> None:
    """The server must not accept what the advice in the same response refuses."""
    theirs = replace(_board(hand=("Bear",), lands=LANDS), active_player=YOU)
    with pytest.raises(BadEventError, match="on your own turn"):
        check(CastSpell(ME, InstanceId("h0"), PAYS), theirs, BOOK)


def test_a_land_cannot_be_cast() -> None:
    """CR 305.1: lands are played, not cast, and it is not a matter of timing."""
    with pytest.raises(BadEventError, match="lands are played, not cast"):
        check(CastSpell(ME, InstanceId("h0"), PAYS), _board(hand=("Forest",), lands=LANDS), BOOK)


def test_a_card_the_coach_cannot_name_is_not_castable() -> None:
    """Unknown is not permitted. Treating it as permitted reopened this once."""
    with pytest.raises(BadEventError, match="does not know this card"):
        check(CastSpell(ME, InstanceId("h0"), PAYS), _board(hand=("Mystery",), lands=LANDS), BOOK)


def test_a_card_not_in_hand_is_left_to_the_reducer() -> None:
    """Which says it better, and says it about the state rather than the card."""
    check(CastSpell(ME, InstanceId("nobody"), PAYS), _board(hand=("Bear",)), BOOK)


def test_a_permanent_spell_may_resolve_to_the_battlefield() -> None:
    """CR 608.3."""
    board = _board(stack=("Bear",))
    check(ResolveSpell(ME, InstanceId("s0"), ZoneName.BATTLEFIELD), board, BOOK)


def test_an_instant_may_resolve_to_the_graveyard() -> None:
    """CR 608.2m."""
    board = _board(stack=("Opt",))
    check(ResolveSpell(ME, InstanceId("s0"), ZoneName.GRAVEYARD), board, BOOK)


def test_an_instant_may_not_resolve_onto_the_battlefield() -> None:
    """The bug, arriving from the client side. This is what stops it.

    An Opt on the battlefield is what a child would see for the rest of the
    game, and nothing else in the stack of checks would have caught it: the
    reducer allows either destination because it cannot read a type line.
    """
    board = _board(stack=("Opt",))
    with pytest.raises(BadEventError, match="Opt is an instant or a sorcery"):
        check(ResolveSpell(ME, InstanceId("s0"), ZoneName.BATTLEFIELD), board, BOOK)


def test_a_creature_may_not_resolve_into_the_graveyard() -> None:
    """The mirror, and just as wrong: a Bear you cast is a Bear on the table."""
    board = _board(stack=("Bear",))
    with pytest.raises(BadEventError, match="Grizzly Bears is a permanent spell"):
        check(ResolveSpell(ME, InstanceId("s0"), ZoneName.GRAVEYARD), board, BOOK)


def test_a_spell_the_coach_cannot_name_cannot_resolve() -> None:
    """Nothing about an unknown card says where it goes."""
    board = _board(stack=("Mystery",))
    with pytest.raises(BadEventError, match="does not know this card"):
        check(ResolveSpell(ME, InstanceId("s0"), ZoneName.GRAVEYARD), board, BOOK)


def test_a_spell_not_on_the_stack_is_left_to_the_reducer() -> None:
    check(ResolveSpell(ME, InstanceId("nobody"), ZoneName.GRAVEYARD), _board(), BOOK)
