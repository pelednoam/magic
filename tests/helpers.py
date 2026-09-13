"""Shared builders for engine tests.

Importable (rather than living in ``conftest.py``) because these are used at
module level -- in ``parametrize`` arguments and constants -- where a pytest
fixture cannot reach.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from mtgcoach.carddata.extraction import Confidence, ExtractionResult, Proposal
from mtgcoach.core.abilities import ActivatedAbility, UnmodeledAbility
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.vocabulary import AbilityCost

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.carddata.cards import Card

ME = PlayerId("me")
YOU = PlayerId("you")

DECK_SIZE = 20


def deck(prefix: str, size: int = DECK_SIZE) -> tuple[CardInstance, ...]:
    """A library of distinguishable cards sharing one oracle identity."""
    return tuple(CardInstance(InstanceId(f"{prefix}-{i}"), OracleId("forest")) for i in range(size))


def card_id(prefix: str, index: int) -> InstanceId:
    """The identifier ``deck`` gives the card at ``index``."""
    return InstanceId(f"{prefix}-{index}")


MANA_ABILITY = ActivatedAbility(AbilityCost(tap=True), (ProduceMana("{G}"),))
UNKNOWN_ABILITY = UnmodeledAbility("Choose one", "modal spells are not modelled")


@dataclass(frozen=True, slots=True)
class FakeExtractor:
    """An ``EffectExtractor`` that answers without a model.

    Every test of the extraction pipeline runs through this, so none of them
    invokes a model, waits on a subprocess, or costs anything. One card in three
    is left unmodelled so the coverage paths are exercised.
    """

    failures: tuple[str, ...] = ()

    def extract(self, cards: Sequence[Card]) -> ExtractionResult:
        """Propose a mana ability for most cards, an unmodelled one for some."""
        proposals = tuple(
            Proposal(
                oracle_id=OracleId(card.oracle_id),
                name=card.name,
                abilities=(UNKNOWN_ABILITY,) if index % 3 == 0 else (MANA_ABILITY,),
                confidence=Confidence.HIGH,
                notes="",
            )
            for index, card in enumerate(cards)
        )
        return ExtractionResult(proposals, self.failures)
