"""R07's probe against the *real* document and the *real* card database.

``test_grounding`` and ``test_evidence`` build their own passages and their own
card text, which is right for testing the logic and is exactly why a hand-built
fixture cannot settle this finding. The probe is a claim about what rule 702.19b
says and what Dazzling Angel says, and a fixture that wrote those out would be
testing the fixture. So this reads the installed Comprehensive Rules and the
imported Foundations store, and asks two questions of them:

- does the evidence a real question retrieves actually contain the words a
  correct answer needs, so that the check is not simply refusing everything;
- and is the probe -- fluent, real rule number, unsupported conclusion --
  refused.

Skipped, loudly, when either is not installed. The rules are Wizards' document
and are not vendored (see ``rules.library``), and the card store is a local
import, so a fresh checkout has neither; a green run here would otherwise say
nothing at all.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from mtgcoach.api.cards import build
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.core.ids import OracleId, SetCode
from mtgcoach.rules.answer import Answer, cited, grounded
from mtgcoach.rules.grounding import Given
from mtgcoach.rules.library import index_at, rules_path

if TYPE_CHECKING:
    from mtgcoach.rules.search import RuleIndex

DB: Final = Path("data/cards.sqlite3")
DATA: Final = Path("data")
FDN: Final = SetCode("FDN")

#: A question whose retrieval really does return 702.19b. The probe is about
#: that rule, so a question that did not retrieve it would prove nothing.
QUESTION: Final = "my creature with trample is blocked, how much damage goes to the player"

#: The answer R07 constructed, word for word.
PROBE: Final = Answer(
    answer="Trample doubles all damage.",
    in_short="Your creature hits twice as hard.",
    citations=("702.19b",),
)


@pytest.fixture(scope="module")
def index() -> RuleIndex:
    """The installed Comprehensive Rules, indexed, or a skip."""
    path = rules_path(DATA)
    if not path.is_file():
        pytest.skip(f"{path} is not installed; see rules.library")
    return index_at(path)


@pytest.fixture(scope="module")
def angel() -> str:
    """The real printed text of Dazzling Angel, or a skip."""
    if not DB.is_file():
        pytest.skip(f"{DB} is not imported; run `mtgcoach sets add FDN`")
    with CardStore.open(str(DB)) as store:
        cards = store.cards_in_set(FDN)
    catalogue = build(cards, effects_path(DATA, FDN))
    named = (oid for oid, card in catalogue.cards.items() if card.name == "Dazzling Angel")
    found = next(named, None)
    if found is None:
        pytest.skip("Dazzling Angel is not in the imported set")
    return catalogue.text(OracleId(found))


def test_the_shipped_card_really_does_carry_the_instruction(angel: str) -> None:
    """Half (a), against the store rather than against a fixture.

    The sentence a question about this card turns on. It was in the database all
    along and never reached the prompt, which is the whole of the first half of
    R07 -- so this asserts the store still has it and ``Catalogue.text`` still
    hands it over.
    """
    assert "you gain 1 life" in angel
    assert "Whenever another creature you control enters" in angel


def test_the_probe_is_refused_against_the_real_rule(index: RuleIndex, angel: str) -> None:
    """The finding, closed, with nothing hand-written in the evidence.

    702.19b is retrieved for this question and says nothing about doubling, so
    the arithmetic in the answer came from somewhere other than the evidence.
    ``cited`` still passes it -- that check is about where the reference came
    from -- and ``grounded`` is what refuses it.
    """
    passages = index.search(QUESTION)
    assert "702.19b" in [p.reference for p in passages]
    given = Given(cards=(angel,), keywords=index.keywords)
    assert cited(PROBE, passages)
    assert not grounded(PROBE, passages, given)


def test_the_real_rule_does_not_double_anything(index: RuleIndex) -> None:
    """Checked against the document rather than from memory, as §8 requires."""
    passages = index.search(QUESTION)
    text = next(p.text for p in passages if p.reference == "702.19b")
    assert "assigns damage to the creature(s) blocking it" in text
    assert "double" not in text.lower()
    assert "twice" not in text.lower()


def test_a_correct_answer_about_the_same_passages_is_not_refused(
    index: RuleIndex, angel: str
) -> None:
    """The other direction, which matters as much.

    A check that refused correct answers would be switched off, and the probe
    would come back with it. Both of these stay inside what the real retrieval
    supplies: the first repeats 702.19b, the second describes the board's own
    card using the ability that card's real text names.
    """
    passages = index.search(QUESTION)
    given = Given(cards=(angel,), keywords=index.keywords)
    for said in (
        (
            "Assign lethal damage to each blocking creature first; the rest may be "
            "assigned to the player you are attacking."
        ),
        "Your Dazzling Angel has flying, so only a creature with flying or reach can block it.",
    ):
        answer = Answer(
            answer=said, in_short="The extra damage gets through.", citations=("702.19b",)
        )
        assert grounded(answer, passages, given), said


def test_ordinary_english_that_collides_with_the_real_keyword_list_is_allowed(
    index: RuleIndex,
) -> None:
    """Against all the names the real document defines, awkward ones included.

    The excerpt defines three keywords, so the collisions that matter -- recover,
    fear, shadow, storm, plot -- only exist against the real list. These
    sentences are English and an answer is allowed to contain them.
    """
    assert {"recover", "fear", "shadow", "storm", "plot"} <= index.keywords.names
    given = Given(keywords=index.keywords)
    said = Answer(
        answer=(
            "You recover the card at end of turn, so there is no need to fear the "
            "attack; the plot of the game does not change and no storm is coming."
        ),
        in_short="You get it back.",
        citations=("702.19b",),
    )
    assert grounded(said, index.search(QUESTION), given)
