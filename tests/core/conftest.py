"""Shared fixtures for the core engine tests."""

from __future__ import annotations

import pytest
from helpers import ME, YOU, deck

from mtgcoach.core.state import GameState, start_game


@pytest.fixture
def game() -> GameState:
    """A fresh two-player game with ``me`` on the play."""
    return start_game({ME: deck("m"), YOU: deck("y")}, ME)
