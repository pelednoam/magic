"""The sealed effect fixture: reviewed data the engine reads at runtime.

Separate from a proposal on purpose. A proposal is what a model suggested and a
person has not looked at yet; a sealed fixture is what was accepted. Nothing at
runtime reads proposals, and sealing is the only way data crosses that line.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.carddata.abilitycodec import decode, encode
from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    as_array,
    optional_str,
    require_object,
    require_str,
)
from mtgcoach.core.ids import OracleId

if TYPE_CHECKING:
    from pathlib import Path

    from mtgcoach.core.abilities import Ability


@dataclass(frozen=True, slots=True)
class CardAbilities:
    """One card's reviewed abilities."""

    oracle_id: OracleId
    name: str
    abilities: tuple[Ability, ...]
    notes: str = ""

    @property
    def is_modelled(self) -> bool:
        """Whether every ability on this card is expressible.

        A card with no abilities at all counts: a vanilla creature is fully
        understood, it simply does nothing.
        """
        return not any(type(a).__name__ == "UnmodeledAbility" for a in self.abilities)


def dump(path: Path, cards: list[CardAbilities]) -> None:
    """Write a fixture, sorted by name so the bytes are reproducible.

    The manifest checksums these exact bytes, so a stable order is not a tidiness
    preference -- without it the checksum would change on every regeneration and
    say nothing.
    """
    body = {
        "cards": [
            {
                "oracle_id": card.oracle_id,
                "name": card.name,
                "notes": card.notes,
                "abilities": [encode(a) for a in card.abilities],
            }
            for card in sorted(cards, key=lambda c: c.name)
        ]
    }
    path.write_text(json.dumps(body, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load(path: Path) -> tuple[CardAbilities, ...]:
    """Read a sealed fixture.

    Raises:
        MalformedJsonError: If the document or any card in it is malformed. A
            sealed fixture has been reviewed, so anything wrong with it is a
            corruption rather than an expected input.
    """
    obj = require_object(json.loads(path.read_text(encoding="utf-8")), path.name)
    rows = as_array(obj.get("cards"))
    if rows is None:
        msg = f"{path.name}: 'cards' must be a list"
        raise MalformedJsonError(msg)
    return tuple(_card(row, path.name) for row in rows)


def _card(value: object, context: str) -> CardAbilities:
    obj = require_object(value, context)
    name = require_str(obj, "name", context)
    return CardAbilities(
        oracle_id=OracleId(require_str(obj, "oracle_id", name)),
        name=name,
        abilities=tuple(decode(a, name) for a in as_array(obj.get("abilities")) or []),
        notes=optional_str(obj, "notes"),
    )
