"""The one paraphrase that replaces a word rather than adding to it.

"Die" does not compete with the rules' own wording -- it wins, for the wrong
rule. The document's only uses of the term are the planar die and the heading
of rule 706, "Rolling a Die", and a heading outranks a phrase. So "when does my
creature die from damage?" returned eight passages, every one about dice, and
CR 700.4 -- which defines the word -- was not among them.
"""

from __future__ import annotations

import pytest

from mtgcoach.rules.instead import instead_of
from mtgcoach.rules.terms import query


@pytest.mark.parametrize(
    "question",
    [
        "when does my creature die from damage?",
        "does my creature dying trigger anything?",
        "is my bear dead if it takes 2 damage?",
        "what happens when a creature dies in combat?",
    ],
)
def test_a_question_about_a_creature_dying_sets_the_word_aside(question: str) -> None:
    assert "die" in instead_of(question)


@pytest.mark.parametrize(
    "question",
    [
        "how do I roll the planar die?",
        "what does rolling a die do in Planechase?",
        "how does trample work?",
        "can a tapped creature block?",
    ],
)
def test_every_other_question_keeps_all_of_its_words(question: str) -> None:
    """Including the questions that really are about dice.

    The scope is a creature, damage or combat. A Planechase question has none
    of those, so the word it needs is left alone -- the fix must not make the
    other question unanswerable in order to answer this one.
    """
    assert instead_of(question) == frozenset()


def test_the_word_is_gone_from_the_query_and_the_phrase_is_in_it() -> None:
    """Both halves, because either alone would not have worked.

    Adding the phrases without dropping the word left rule 706 winning on its
    heading; dropping the word without the phrases left nothing to match.
    """
    built = query("when does my creature die from damage?")
    assert '"die"' not in built
    assert '"put into a graveyard from the battlefield"' in built
    assert '"lethal damage"' in built


def test_a_question_that_is_only_the_set_aside_word_still_searches() -> None:
    """The backstop `query` already has, reached by this new channel.

    Setting words aside may not leave an empty query: `search` reads that as
    "the rules cannot be looked up for this" and answers with no passages at
    all. A collision ranks the wrong passage; an empty query ranks none.
    """
    assert query("creature dies") != ""
