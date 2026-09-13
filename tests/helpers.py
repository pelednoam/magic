"""Shared builders for engine tests.

Importable (rather than living in ``conftest.py``) because these are used at
module level -- in ``parametrize`` arguments and constants -- where a pytest
fixture cannot reach.
"""

from __future__ import annotations

from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId

ME = PlayerId("me")
YOU = PlayerId("you")

DECK_SIZE = 20


def deck(prefix: str, size: int = DECK_SIZE) -> tuple[CardInstance, ...]:
    """A library of distinguishable cards sharing one oracle identity."""
    return tuple(CardInstance(InstanceId(f"{prefix}-{i}"), OracleId("forest")) for i in range(size))


def card_id(prefix: str, index: int) -> InstanceId:
    """The identifier ``deck`` gives the card at ``index``."""
    return InstanceId(f"{prefix}-{index}")
