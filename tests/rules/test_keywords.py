"""Telling a Magic keyword from the ordinary English word it is spelled like.

Found live: *"what happens when my hit points reach zero?"* returned the four
passages titled **Reach**, the keyword ability, and nothing about losing the
game. "Reach" appears seventeen times in the whole document, nearly all of them
the keyword, so it is a rare term and bm25 weights it heavily.

The risk runs the other way too, and further: a question about a keyword is
much commoner than one that merely contains a keyword, and dropping the word
from "what about deathtouch?" leaves a question that retrieves nothing. So
these tests are mostly about what is *not* set aside.
"""

from __future__ import annotations

from helpers_rules import PASSAGES
from mtgcoach.rules.keywords import names_in, ordinary
from mtgcoach.rules.terms import query

KEYWORDS = names_in(PASSAGES)


def test_the_keyword_names_come_off_the_document() -> None:
    """Not a list in the source.

    There are 160 of them in the real rules and Wizards add several a year, so
    a list written out in the module would be wrong by the next set -- and this
    has to work on sets nobody has printed.
    """
    assert {"deathtouch", "reach", "trample"} == KEYWORDS


def test_a_two_word_keyword_is_not_collected() -> None:
    """A two-word keyword cannot be typed by accident.

    "First strike" is not a thing somebody writes without meaning it, and the
    phrase is what makes the rule findable.
    """
    assert not any(" " in name for name in names_in(PASSAGES))


def test_a_number_after_the_word_makes_it_a_verb() -> None:
    """The question this was written for."""
    assert ordinary("what happens when my hit points reach zero?", KEYWORDS) == {"reach"}


def test_a_digit_after_the_word_counts_too() -> None:
    assert ordinary("what happens when I reach 0 life?", KEYWORDS) == {"reach"}


def test_a_subject_pronoun_before_the_word_makes_it_a_verb() -> None:
    assert ordinary("what happens if I reach zero life?", KEYWORDS) == {"reach"}


def test_a_question_about_the_keyword_keeps_it() -> None:
    """Every one of these would retrieve nothing with the word removed."""
    for question in [
        "what does reach do?",
        "can a creature with reach block a flyer?",
        "does it have reach?",
        "what about deathtouch?",
        "how does trample work when blocked?",
        "trample damage",
        "is reach any good?",
    ]:
        assert ordinary(question, KEYWORDS) == frozenset(), question


def test_a_word_that_is_not_a_keyword_is_never_set_aside() -> None:
    """Only the document's own keyword names are candidates at all."""
    assert ordinary("how many cards do I draw?", KEYWORDS) == frozenset()
    assert ordinary("does the damage reach the player?", KEYWORDS) == frozenset()


def test_an_index_with_no_keywords_sets_nothing_aside() -> None:
    """The default, and what every caller that does not pass them gets."""
    assert ordinary("what happens when my hit points reach zero?", frozenset()) == frozenset()


def test_the_word_is_gone_from_the_query() -> None:
    """Dropped rather than down-weighted.

    A keyword name is rare in the document, so it scores heavily, and the
    document has no other use for the word -- keeping it can only pull the
    wrong passages up.
    """
    built = query("what happens when my hit points reach zero?", KEYWORDS)
    assert '"reach"' not in built
    assert '"points"' in built


def test_the_word_stays_when_the_question_is_about_the_keyword() -> None:
    assert '"reach"' in query("what does reach do?", KEYWORDS)


def test_a_question_that_is_only_a_keyword_used_as_a_verb_still_has_words() -> None:
    """Removing the word must not empty the query.

    An empty query means "the rules cannot be looked up for this", which is a
    much stronger statement than "one of your words was ambiguous".
    """
    assert query("my life points reach zero", KEYWORDS) != ""
