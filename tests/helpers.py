"""Shared builders for engine tests.

Importable (rather than living in ``conftest.py``) because these are used at
module level -- in ``parametrize`` arguments and constants -- where a pytest
fixture cannot reach.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

from mtgcoach.carddata.extraction import Confidence, ExtractionResult, Proposal
from mtgcoach.core import priority
from mtgcoach.core.abilities import ActivatedAbility, UnmodeledAbility
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.combat.model import Creature
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.events import AdvanceStep, PassPriority
from mtgcoach.core.facts import CardFacts
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId
from mtgcoach.core.manacost import parse
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.reduce import apply
from mtgcoach.core.vocabulary import AbilityCost

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.carddata.cards import Card
    from mtgcoach.core.state import GameState
    from mtgcoach.core.steps import Step

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


def facts(
    name: str,
    cost: str = "",
    *keywords: str,
    power: int | None = None,
    toughness: int | None = None,
    creature: bool = False,
    land: bool = False,
    instant: bool = False,
    permanent: bool | None = None,
) -> CardFacts:
    """Card facts for a rules test, named so failures read like the board.

    ``permanent`` defaults to what the other flags imply: a land or a creature
    stays on the battlefield (CR 110.1) and anything else here does not. Spelled
    out rather than left to the caller because a fixture that forgot it made a
    Grizzly Bears resolve into the graveyard -- which is the fixture lying about
    the rules, and the one thing no fixture in this project may do.
    """
    return CardFacts(
        oracle_id=OracleId(name),
        name=name,
        cost=parse(cost),
        is_land=land,
        is_creature=creature,
        is_instant_speed=instant,
        is_permanent=(land or creature) if permanent is None else permanent,
        power=power,
        toughness=toughness,
        keywords=frozenset(keywords),
    )


_serial = itertools.count()


def creature(name: str, power: int, toughness: int, *keywords: str) -> Creature:
    """A settled, untapped creature on the battlefield.

    Each call gets its own ``InstanceId``. Deriving it from the name made two
    copies of one card a single creature to the engine -- damage on either
    killed both, blocks on either applied to both -- and two copies of a card is
    the most ordinary board state in Magic.
    """
    instance = InstanceId(f"{name}#{next(_serial)}")
    return Creature(
        Permanent(CardInstance(instance, OracleId(name))).settle(),
        facts(name, "", *keywords, power=power, toughness=toughness, creature=True),
    )


def at_step(
    state: GameState,
    step: Step,
    active: PlayerId | None = None,
    holder: PlayerId | None = None,
) -> GameState:
    """The same board, at ``step``, with priority handed out as it would be.

    Every test that used to write ``replace(game, step=...)`` needs this now:
    the step no longer tells you who may act. ``GameState.priority`` defaults
    to None because a game begins in the untap step, where that is the right
    answer -- so a board dropped into a main phase by hand has nobody able to
    do anything until somebody hands priority out, and ``turn.advance`` is what
    does it in a game that is really played (CR 117.3a).

    ``holder`` overrides who holds it, for the one case a test cannot reach
    otherwise: the *nonactive* player holding priority, which is the state the
    moment the active player passes (CR 117.3d) and the only way anybody casts
    an instant on somebody else's turn.
    """
    whose = active if active is not None else state.active_player
    handed = priority.begins(replace(state, step=step, active_player=whose))
    return handed if holder is None else replace(handed, priority=holder)


def all_pass(state: GameState) -> GameState:
    """Every player who still can, passes (CR 117.3d).

    What it takes to make the top of the stack resolve, or the step end
    (CR 117.4). Written out rather than folded into ``stepped`` because half
    the tests want to stop here: this is the state a resolution is legal from,
    and the state a *second* spell can still be cast in.
    """
    for player in priority.yet_to_pass(state):
        state = apply(state, PassPriority(player))
    return state


def stepped(state: GameState) -> GameState:
    """End this step the way CR 500.2 says it ends: all pass, then it ends.

    A bare ``AdvanceStep`` is refused now, and that refusal is the finding this
    helper exists because of: a step does not end because the stack happens to
    be empty, it ends because each player has had the chance to add to it and
    declined.
    """
    return apply(all_pass(state), AdvanceStep())
