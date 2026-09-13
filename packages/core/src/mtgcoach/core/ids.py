"""Distinct identifier types.

These are ``NewType`` wrappers rather than bare ``str`` aliases so that the
type checker rejects passing a player id where a card id is expected. They are
free at runtime; the guarantee is entirely static, and
``tests/core/test_ids.py`` asserts that the distinction still holds.
"""

from __future__ import annotations

from typing import NewType

#: Identifies a card by rules behaviour, independent of printing. Every layer
#: keys on this: two printings of the same card are the same card to the engine.
OracleId = NewType("OracleId", str)

#: Identifies one physical card in one game. Two copies of the same card in a
#: deck share an ``OracleId`` but never an ``InstanceId``.
InstanceId = NewType("InstanceId", str)

#: Identifies a player within a single game.
PlayerId = NewType("PlayerId", str)

#: A Scryfall set code, e.g. ``FDN``.
SetCode = NewType("SetCode", str)
