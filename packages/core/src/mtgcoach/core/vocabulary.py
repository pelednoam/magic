"""The vocabulary effects are written in.

Durations, counter kinds and token shapes are not effects; they are the words
effects use. Separated when ``effects`` outgrew the module size limit, which
turned out to be the right seam rather than an arbitrary one.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class Duration(StrEnum):
    """How long a continuous effect lasts."""

    UNTIL_END_OF_TURN = "until_end_of_turn"
    WHILE_ATTACHED = "while_attached"
    PERMANENT = "permanent"


class CounterKind(StrEnum):
    """Kinds of counter the box can produce."""

    PLUS_ONE_PLUS_ONE = "+1/+1"
    MINUS_ONE_MINUS_ONE = "-1/-1"


@dataclass(frozen=True, slots=True)
class TokenSpec:
    """A creature or artifact token an effect creates."""

    name: str
    type_line: str
    power: int | None = None
    toughness: int | None = None
    colors: frozenset[str] = field(default_factory=frozenset[str])
    keywords: frozenset[str] = field(default_factory=frozenset[str])


class TriggerEvent(StrEnum):
    """What makes a triggered ability go off.

    Drawn from the Beginner Box: these are the conditions its cards actually
    use, not a survey of every trigger Magic has.
    """

    ENTERS = "enters"
    DIES = "dies"
    ATTACKS = "attacks"
    BLOCKS = "blocks"
    DEALS_COMBAT_DAMAGE = "deals_combat_damage"
    ANOTHER_CREATURE_ENTERS = "another_creature_enters"
    YOU_GAIN_LIFE = "you_gain_life"
    YOU_CAST_SPELL = "you_cast_spell"
    BEGINNING_OF_UPKEEP = "beginning_of_upkeep"
    END_STEP = "end_step"


class Restriction(StrEnum):
    """A thing a permanent is stopped from doing."""

    CANT_ATTACK = "cant_attack"
    CANT_BLOCK = "cant_block"
    DOESNT_UNTAP = "doesnt_untap"
    MUST_BE_BLOCKED = "must_be_blocked"


@dataclass(frozen=True, slots=True)
class AbilityCost:
    """What activating an ability costs.

    ``{T}: Add {G}`` is tap-only; ``{7}, {T}, Sacrifice this artifact:`` is all
    three. Mana is kept as a cost string so the solver can parse it once, in one
    place, rather than each producer inventing its own encoding.
    """

    mana: str = ""
    tap: bool = False
    sacrifice_self: bool = False

    @property
    def is_free(self) -> bool:
        """Whether activating costs nothing at all."""
        return not self.mana and not self.tap and not self.sacrifice_self
