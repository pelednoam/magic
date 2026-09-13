"""Turning oracle text into effects, once, at build time.

This is the only place an LLM is asked to do the hard part -- reading English
rules text and writing down what it means -- and it happens offline, in bulk,
with a human reviewing the result before anything is sealed. At runtime the
engine reads committed data and never asks a model anything.

A proposal is not an answer. It carries the model's own confidence and notes so
that ``effects review`` can put the doubtful ones in front of a person first,
rather than presenting 124 cards as equally trustworthy.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

from mtgcoach.core.amounts import Quantity
from mtgcoach.core.targets import Condition, Controller, TargetKind
from mtgcoach.core.vocabulary import (
    CounterKind,
    Duration,
    Restriction,
    TriggerEvent,
)
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.carddata.cards import Card
    from mtgcoach.core.abilities import Ability
    from mtgcoach.core.ids import OracleId

#: Ability kinds. An ability says *when*; the effects inside say *what*.
ABILITY_KINDS: tuple[str, ...] = (
    "spell{effects}  -- an instant or sorcery's own effects",
    "triggered{event,subject?,effects}",
    "activated{cost:{mana,tap,sacrifice_self},effects}",
    "static_modifier{power,toughness,affects}",
    "static_restriction{restriction,affects}",
    "unmodeled{text,reason}",
)

#: Effect kinds, in the encoder's vocabulary. Built from the code rather than
#: written out, so the prompt cannot describe a schema the codec does not have.
EFFECT_KINDS: tuple[str, ...] = (
    "deal_damage{amount,target,source?}",
    "destroy{target}",
    "exile{target}",
    "move_to{target,to_zone}",
    "counter_spell{target}",
    "draw{count,who}",
    "discard{count,who}",
    "change_life{amount,who}",
    "scry{count}",
    "modify_stats{power,toughness,target,duration}",
    "grant_keywords{keywords,target,duration}",
    "put_counters{counter,count,target}",
    "set_tapped{tapped,target}",
    "create_tokens{count,token}",
    "produce_mana{mana,amount}",
    "unmodeled{text,reason}",
)


class Confidence(StrEnum):
    """How sure the extractor is, in its own words."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


@dataclass(frozen=True, slots=True)
class Proposal:
    """One card's proposed effects, awaiting review."""

    oracle_id: OracleId
    name: str
    abilities: tuple[Ability, ...]
    confidence: Confidence
    notes: str = ""

    @property
    def needs_attention(self) -> bool:
        """Whether a reviewer should look at this one before the easy ones."""
        return self.confidence is not Confidence.HIGH or any(
            type(a).__name__ == "UnmodeledAbility" for a in self.abilities
        )


@dataclass(frozen=True, slots=True)
class ExtractionResult:
    """What one extraction run produced."""

    proposals: tuple[Proposal, ...] = ()
    failures: tuple[str, ...] = field(default_factory=tuple[str, ...])


class EffectExtractor(Protocol):
    """Something that can propose effects for cards.

    A protocol so the pipeline can be tested without invoking a model at all,
    and so the backing implementation -- the Claude CLI, the API, or a recorded
    fixture -- is a swap rather than a rewrite.
    """

    def extract(self, cards: Sequence[Card]) -> ExtractionResult:
        """Propose effects for each card, in order."""
        ...


def vocabulary() -> str:
    """The schema, described for a prompt, generated from the code itself.

    Written out by hand this would drift from the codec the first time an enum
    gained a member, and the prompt would then ask for values the decoder
    rejects.
    """
    lines = [
        "ability kinds: " + ", ".join(ABILITY_KINDS),
        "trigger event: " + ", ".join(e.value for e in TriggerEvent),
        "restriction: " + ", ".join(r.value for r in Restriction),
        "effect kinds: " + ", ".join(EFFECT_KINDS),
        "target.kinds: " + ", ".join(k.value for k in TargetKind),
        "target.controller: " + ", ".join(c.value for c in Controller),
        "target.conditions: " + ", ".join(c.value for c in Condition),
        "duration: " + ", ".join(d.value for d in Duration),
        "counter: " + ", ".join(c.value for c in CounterKind),
        "to_zone: " + ", ".join(z.value for z in ZoneName),
        "amount: an integer, or {quantity: one of " + ", ".join(q.value for q in Quantity) + "}",
    ]
    return "\n".join(lines)


def describe(card: Card) -> str:
    """One card, as the extractor sees it."""
    face = card.front
    stats = (
        f" {face.power}/{face.toughness}"
        if face.power is not None and face.toughness is not None
        else ""
    )
    return f"{card.name} | {face.type_line}{stats} | {face.mana_cost}\n{face.oracle_text}"
