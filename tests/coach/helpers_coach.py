"""A card lookup backed by a dict, so a coach test reads like a board."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from helpers import ME, YOU, facts
from mtgcoach.core import priority
from mtgcoach.core.abilities import Ability, ActivatedAbility, unmodelled_reasons
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.carrying import not_carried_out as _not_carried_out
from mtgcoach.core.effects import ProduceMana
from mtgcoach.core.facts import CardFacts
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.player import PlayerState
from mtgcoach.core.state import GameState
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import AbilityCost

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def taps_for(mana: str) -> ActivatedAbility:
    """``{T}: Add <mana>`` -- the most ordinary ability in the game."""
    return ActivatedAbility(AbilityCost(tap=True), (ProduceMana(mana),))


@dataclass(frozen=True, slots=True)
class Book:
    """Everything the coach knows about cards, written out by hand."""

    cards: Mapping[str, CardFacts] = field(default_factory=dict[str, CardFacts])
    rules: Mapping[str, tuple[Ability, ...]] = field(default_factory=dict[str, tuple[Ability, ...]])

    def facts(self, oracle_id: OracleId) -> CardFacts | None:
        """The engine's view of the card, or None when it is not in the book."""
        return self.cards.get(str(oracle_id))

    def abilities(self, oracle_id: OracleId) -> Sequence[Ability]:
        """The card's modelled abilities, empty when it has none."""
        return self.rules.get(str(oracle_id), ())

    def name(self, oracle_id: OracleId) -> str:
        """The printed name, or the identifier when the book has no card."""
        card = self.cards.get(str(oracle_id))
        return card.name if card is not None else str(oracle_id)

    def modelled(self, oracle_id: OracleId) -> bool:
        """Whether the book covers this card, all the way down."""
        abilities = self.rules.get(str(oracle_id))
        if abilities is None:
            return False
        return not any(unmodelled_reasons(ability) for ability in abilities)

    def not_carried_out(self, oracle_id: OracleId) -> tuple[str, ...]:
        """What the engine will not do if this card is played.

        The same two answers the real catalogue gives, and for the same reason
        -- a book that reported every unreviewed card as fully handled would
        make the disclosure tests pass while disclosing nothing.
        """
        abilities = self.rules.get(str(oracle_id))
        if abilities is None:
            return ("anything it does -- this card has not been reviewed",)
        return _not_carried_out(abilities)


def land(name: str, mana: str) -> tuple[CardFacts, tuple[Ability, ...]]:
    """A basic land and its mana ability."""
    return facts(name, land=True), (taps_for(mana),)


def instance(oracle: str, suffix: str = "1") -> CardInstance:
    """One physical copy of a card."""
    return CardInstance(InstanceId(f"{oracle}-{suffix}"), OracleId(oracle))


def on_battlefield(
    oracle: str, suffix: str = "1", *, tapped: bool = False, sick: bool = False
) -> Permanent:
    """A permanent, settled unless it is said to be summoning sick."""
    permanent = Permanent(instance(oracle, suffix))
    if not sick:
        permanent = permanent.settle()
    return permanent.tap() if tapped else permanent


def game(
    *,
    hand: tuple[str, ...] = (),
    battlefield: tuple[str, ...] = (),
    theirs: tuple[str, ...] = (),
    step: Step = Step.PRECOMBAT_MAIN,
    active: str = "me",
    life: int = 20,
) -> GameState:
    """A two-player game, written as the two boards you can see.

    Priority is handed out the way entering the step hands it out (CR 117.3a),
    because a board with nobody able to act is a board where every card in hand
    comes back with one reason and it is not the one the test is about.
    """
    mine = PlayerState(
        library=(),
        hand=tuple(instance(o, str(i)) for i, o in enumerate(hand)),
        battlefield=tuple(on_battlefield(o, str(i)) for i, o in enumerate(battlefield)),
        graveyard=(),
        exile=(),
    )
    yours = PlayerState(
        library=(),
        hand=(),
        battlefield=tuple(on_battlefield(o, f"y{i}") for i, o in enumerate(theirs)),
        graveyard=(),
        exile=(),
        life=life,
    )
    return priority.begins(
        GameState(
            turn=1,
            active_player=ME if active == "me" else YOU,
            step=step,
            players={ME: mine, YOU: yours},
        )
    )
