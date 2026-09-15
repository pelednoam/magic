"""The prompt a real board and the real rules produce.

``test_question`` builds its own cards, which is right for testing the layout
and cannot settle R07: the finding is that a card's *actual* instruction never
reached the prompt, and a test that writes the instruction into a fixture is
testing the fixture. So this reads the imported Foundations store and the
installed Comprehensive Rules and asks whether the sentence a question turns on
is in the text sent to the model.

It also pins the size. The prompt grew when the card text went in -- that is
the trade this change made -- and a bound written down is the difference
between a trade and a leak.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from mtgcoach.api.cards import Catalogue, build
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.coach.report import advise
from mtgcoach.coach.table import table
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId, PlayerId, SetCode
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.player import PlayerState
from mtgcoach.core.state import GameState
from mtgcoach.core.steps import Step
from mtgcoach.rules.library import index_at, rules_path
from mtgcoach.rules.question import brief

if TYPE_CHECKING:
    from mtgcoach.rules.search import RuleIndex

DB: Final = Path("data/cards.sqlite3")
DATA: Final = Path("data")
FDN: Final = SetCode("FDN")
ME: Final = PlayerId("me")
YOU: Final = PlayerId("you")

#: A creature whose ability is a beginner's question, a land, a trick in hand
#: and something on the other side. Chosen because each is really in the set
#: and each really has text: a board of vanilla creatures would pass whatever
#: the prompt did with card text.
MINE: Final = ("Dazzling Angel", "Plains", "Plains")
THEIRS: Final = ("Vampire Spawn",)
HAND: Final = ("Giant Growth",)

#: What one prompt may reasonably cost. Eight retrieved passages of the real
#: document plus a kitchen-table board: measured at a little over 5,000
#: characters, and generous room above that so an ordinary rewording does not
#: fail the gate. It is here because the card text is the thing that grew the
#: prompt, and a growth nobody bounded is how a prompt starts being truncated
#: by something that will not say so.
MOST: Final = 12_000


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    """The real Foundations catalogue, or a skip."""
    if not DB.is_file():
        pytest.skip(f"{DB} is not imported; run `mtgcoach sets add FDN`")
    with CardStore.open(str(DB)) as store:
        cards = store.cards_in_set(FDN)
    if not cards:
        pytest.skip("no FDN cards imported")
    return build(cards, effects_path(DATA, FDN))


@pytest.fixture(scope="module")
def index() -> RuleIndex:
    """The installed Comprehensive Rules, indexed, or a skip."""
    path = rules_path(DATA)
    if not path.is_file():
        pytest.skip(f"{path} is not installed; see rules.library")
    return index_at(path)


def _oracle(catalogue: Catalogue, name: str) -> OracleId:
    """One card's oracle id, by the name printed on it."""
    found = next((oid for oid, card in catalogue.cards.items() if card.name == name), None)
    assert found is not None, f"{name} is not in the imported set"
    return OracleId(found)


def _position(catalogue: Catalogue) -> GameState:
    """A real board, with real cards on it."""

    def held(names: tuple[str, ...]) -> tuple[CardInstance, ...]:
        return tuple(
            CardInstance(InstanceId(f"{name}-{at}"), _oracle(catalogue, name))
            for at, name in enumerate(names)
        )

    mine = PlayerState(
        library=(),
        hand=held(HAND),
        battlefield=tuple(Permanent(card).settle() for card in held(MINE)),
        graveyard=(),
        exile=(),
    )
    theirs = PlayerState(
        library=(),
        hand=(),
        battlefield=tuple(Permanent(card).settle() for card in held(THEIRS)),
        graveyard=(),
        exile=(),
    )
    return GameState(
        turn=3, active_player=ME, step=Step.PRECOMBAT_MAIN, players={ME: mine, YOU: theirs}
    )


def _prompt(catalogue: Catalogue, index: RuleIndex, question: str) -> str:
    """The whole prompt for a question asked over that board."""
    state = _position(catalogue)
    return brief(
        question,
        index.search(question),
        advise(state, ME, catalogue),
        table(state, ME, catalogue),
    )


def test_a_question_about_an_ability_gets_the_cards_exact_text(
    catalogue: Catalogue, index: RuleIndex
) -> None:
    """R07's acceptance test: "card-ability questions receive exact card text".

    The board used to reach the model as "Dazzling Angel, 2/3, Flying, has
    rules text not shown here", so the one sentence that answers this question
    was the one thing missing from the prompt.
    """
    text = _prompt(catalogue, index, "does my Dazzling Angel gain me life when I play a creature?")
    assert "Whenever another creature you control enters, you gain 1 life." in text
    assert "not shown here" not in text


def test_the_text_of_a_card_in_hand_and_on_the_other_side_arrives_too(
    catalogue: Catalogue, index: RuleIndex
) -> None:
    """A question is as often about the trick in hand or the attacker opposite."""
    text = _prompt(catalogue, index, "what does giant growth do to my creature?")
    assert "+3/+3" in text
    assert "each opponent loses 2 life" in text


def test_a_repeated_card_is_quoted_once(catalogue: Catalogue, index: RuleIndex) -> None:
    """Two Plains are one card. The board lines still list both permanents."""
    text = _prompt(catalogue, index, "how many lands can I play?")
    assert text.count("Plains: ({T}: Add {W}.)") == 1
    assert text.count("    - Plains") == 2


def test_the_prompt_stays_within_its_budget(catalogue: Catalogue, index: RuleIndex) -> None:
    """The trade, written down. See ``MOST``."""
    text = _prompt(catalogue, index, "does my Dazzling Angel gain me life?")
    assert len(text) < MOST
