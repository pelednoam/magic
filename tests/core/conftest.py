"""Shared fixtures for the core engine tests."""

from __future__ import annotations

import pytest

from helpers import ME, YOU, at_step, deck
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step


@pytest.fixture
def game() -> GameState:
    """A fresh two-player game with ``me`` on the play.

    At the untap step, where nobody receives priority (CR 502.4) -- which is
    where a game really starts and is the reason so many of these tests take
    ``main`` instead.
    """
    return start_game({ME: deck("m"), YOU: deck("y")}, ME)


@pytest.fixture
def main() -> GameState:
    """The same game in ``me``'s precombat main phase, ``me`` holding priority.

    Anything about *doing* something needs this rather than ``game``: casting a
    spell, playing a land and passing all take priority (CR 117.1a, CR 116.2a),
    and at the untap step there is none to take. Casting used to work there,
    because nothing checked.
    """
    return at_step(start_game({ME: deck("m"), YOU: deck("y")}, ME), Step.PRECOMBAT_MAIN)
