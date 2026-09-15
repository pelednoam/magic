"""A tiny two-card world, enough for a whole game to be played in a test.

Real self-play runs on the Foundations database. These tests need a board that
fits on a screen, so the deck is forests and bears and nothing else -- which is
sufficient, because every module under test is about applying and watching
events rather than about which card was played.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from helpers import facts
from helpers_coach import Book, land
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import Step
from mtgcoach.selfplay.passing import ending

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState

YOU = PlayerId("you")
THEM = PlayerId("them")

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)

#: Everything either side can be holding.
BOOK = Book(
    cards={"Forest": FOREST, "Grizzly Bears": BEAR},
    rules={"Forest": FOREST_RULES, "Grizzly Bears": ()},
)


def library(seat: PlayerId, forests: int = 12, bears: int = 12) -> tuple[CardInstance, ...]:
    """One player's deck: lands first, so an opening hand can pay for things."""
    made: list[CardInstance] = []
    for number in range(forests + bears):
        name = "Forest" if number % 2 == 0 else "Grizzly Bears"
        made.append(
            CardInstance(
                instance_id=InstanceId(f"{seat}-{number}"),
                oracle_id=OracleId(name),
            )
        )
    return tuple(made)


def game(first: PlayerId = YOU, **sizes: int) -> GameState:
    """A game in progress, both players holding seven, at the untap step."""
    return start_game({YOU: library(YOU, **sizes), THEM: library(THEM, **sizes)}, first)


def main_phase(state: GameState | None = None) -> GameState:
    """A game wound forward to a main phase.

    A game starts at untap, where nothing can be played -- so a test about
    playing a card that starts from `game()` finds an empty hand of options
    and fails for a reason that has nothing to do with it.

    Through ``ending``, the same events the harness itself sends: a step ends
    when both players have passed in succession (CR 500.2), so a bare
    ``AdvanceStep`` is refused and a helper that sent one was leaning on the
    gap this engine has closed.
    """
    state = state if state is not None else game()
    while state.step is not Step.PRECOMBAT_MAIN:
        for event in ending(state):
            state = apply(state, event)
    return state
