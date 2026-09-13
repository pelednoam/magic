"""When a card's effects happen.

The layer the first extraction run showed was missing. ``Effect`` says *what*
happens; nothing said *when*, so a card like "Whenever you gain life, put a
+1/+1 counter on this creature" was discarded whole even though ``PutCounters``
could express its effect perfectly. Across the 124 cards in the box, 47 of 84
unmodelled clauses failed for exactly that reason -- and ``{T}: Add {G}``, the
most ordinary ability in the game, was among them.

Four shapes cover the box:

- a spell's own effects, which happen when it resolves;
- a triggered ability, which waits for an event;
- an activated ability, which waits to be paid for;
- a static ability, which is simply true while the permanent is there.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.effects import Effect
    from mtgcoach.core.targets import TargetSpec
    from mtgcoach.core.vocabulary import AbilityCost, Restriction, TriggerEvent


@dataclass(frozen=True, slots=True)
class Trigger:
    """The condition a triggered ability waits for.

    ``subject`` narrows whose event counts -- "whenever *another creature you
    control* enters" -- and is None when the event needs no subject, as with
    "whenever you gain life".
    """

    event: TriggerEvent
    subject: TargetSpec | None = None


@dataclass(frozen=True, slots=True)
class SpellAbility:
    """What an instant or sorcery does on resolution."""

    effects: tuple[Effect, ...]


@dataclass(frozen=True, slots=True)
class TriggeredAbility:
    """Effects that happen when something else does."""

    trigger: Trigger
    effects: tuple[Effect, ...]


@dataclass(frozen=True, slots=True)
class ActivatedAbility:
    """Effects a player may pay for at will."""

    cost: AbilityCost
    effects: tuple[Effect, ...]

    @property
    def is_mana_ability(self) -> bool:
        """Whether this only makes mana, and so never uses the stack (CR 605.1a)."""
        return bool(self.effects) and all(type(e).__name__ == "ProduceMana" for e in self.effects)


@dataclass(frozen=True, slots=True)
class StaticModifier:
    """A continuous change to power and toughness.

    ``Goblin Oriflamme`` gives attacking creatures you control +1/+0; an Aura's
    "enchanted creature gets +2/+1" is the same shape pointed at its host.
    """

    power: int
    toughness: int
    affects: TargetSpec


@dataclass(frozen=True, slots=True)
class StaticRestriction:
    """A continuous prohibition, as ``Pacifism`` puts on its host."""

    restriction: Restriction
    affects: TargetSpec


@dataclass(frozen=True, slots=True)
class UnmodeledAbility:
    """An ability the schema cannot express, kept verbatim and flagged."""

    text: str
    reason: str


type Ability = (
    SpellAbility
    | TriggeredAbility
    | ActivatedAbility
    | StaticModifier
    | StaticRestriction
    | UnmodeledAbility
)
