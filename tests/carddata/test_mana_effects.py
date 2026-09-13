"""Mana strings: the one field a model writes freehand."""

from __future__ import annotations

import pytest

from mtgcoach.carddata.effectdecode import decode
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.core.effects import ProduceMana


@pytest.mark.parametrize(
    ("given", "expected"),
    [("{G}", "{G}"), ("G", "{G}"), ("r", "{R}"), ("2W", "{2}{W}"), ("", "")],
)
def test_bare_mana_symbols_are_normalised(given: str, expected: str) -> None:
    """The extractor wrote `G` for seven of the box's eight mana abilities.

    Normalising here means the stored form is canonical whichever way it arrived.
    """
    effect = decode({"kind": "produce_mana", "mana": given}, "test")
    assert isinstance(effect, ProduceMana)
    assert effect.mana == expected


@pytest.mark.parametrize("bad", ["add green mana", "{G", "G}", "green"])
def test_a_mana_string_that_is_not_symbols_is_rejected(bad: str) -> None:
    """Every neighbouring field is a closed enum; this one should not be prose."""
    with pytest.raises(MalformedJsonError, match="is not a mana cost"):
        decode({"kind": "produce_mana", "mana": bad}, "test")
