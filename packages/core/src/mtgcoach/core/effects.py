"""What a card does, as a closed union rather than prose.

Every member exists because a card in the Beginner Box needs it. The box's 124
distinct cards were read before this was written, and the shape follows what
they actually say: ``Moment of Triumph`` is a stat change *and* a life gain, so
an ability is a sequence of effects rather than one; ``Bite Down`` deals damage
equal to a creature's power, so amounts are not always numbers; ``Deadly Plot``
offers a choice, so modes exist.

``Unmodeled`` is a first-class member, not an embarrassment. A card the engine
cannot express is still tracked, still recognised, still counted in a library --
the coach simply declines to claim a line and shows the card text instead. The
alternative is a confident wrong answer, which for a tool teaching a child is
the one outcome worth engineering against.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.core.amounts import Amount
    from mtgcoach.core.targets import Controller, TargetSpec
    from mtgcoach.core.zones import ZoneName


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


@dataclass(frozen=True, slots=True)
class DealDamage:
    """Deal damage to a target."""

    amount: Amount
    target: TargetSpec


@dataclass(frozen=True, slots=True)
class Destroy:
    """Destroy a target."""

    target: TargetSpec


@dataclass(frozen=True, slots=True)
class ExileTarget:
    """Exile a target."""

    target: TargetSpec


@dataclass(frozen=True, slots=True)
class MoveTo:
    """Move a target card to another zone -- bounce, reanimate, mill."""

    target: TargetSpec
    to_zone: ZoneName


@dataclass(frozen=True, slots=True)
class CounterSpell:
    """Counter a spell on the stack."""

    target: TargetSpec


@dataclass(frozen=True, slots=True)
class Draw:
    """Draw cards."""

    count: int
    who: Controller


@dataclass(frozen=True, slots=True)
class Discard:
    """Discard cards."""

    count: int
    who: Controller


@dataclass(frozen=True, slots=True)
class ChangeLife:
    """Gain or lose life. Negative amounts are losses."""

    amount: int
    who: Controller


@dataclass(frozen=True, slots=True)
class Scry:
    """Look at the top cards and reorder them."""

    count: int


@dataclass(frozen=True, slots=True)
class ModifyStats:
    """Change power and toughness for a duration."""

    power: int
    toughness: int
    target: TargetSpec
    duration: Duration


@dataclass(frozen=True, slots=True)
class GrantKeywords:
    """Give a target one or more keyword abilities."""

    keywords: frozenset[str]
    target: TargetSpec
    duration: Duration


@dataclass(frozen=True, slots=True)
class PutCounters:
    """Put counters on a target."""

    kind: CounterKind
    count: Amount
    target: TargetSpec


@dataclass(frozen=True, slots=True)
class SetTappedEffect:
    """Tap or untap a target."""

    tapped: bool
    target: TargetSpec


@dataclass(frozen=True, slots=True)
class CreateTokens:
    """Put token permanents onto the battlefield."""

    count: int
    token: TokenSpec


@dataclass(frozen=True, slots=True)
class Unmodeled:
    """A card the engine cannot express, kept verbatim and flagged as such.

    ``reason`` is written for the person reading the audit, not the player.
    """

    text: str
    reason: str


type Effect = (
    DealDamage
    | Destroy
    | ExileTarget
    | MoveTo
    | CounterSpell
    | Draw
    | Discard
    | ChangeLife
    | Scry
    | ModifyStats
    | GrantKeywords
    | PutCounters
    | SetTappedEffect
    | CreateTokens
    | Unmodeled
)
