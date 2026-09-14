"""The paraphrases a beginner uses, and the rules' words for them.

The bug these exist for was found live: *"can a creature that came into play
this turn block?"* retrieved eight passages about blocking and not rule 302.6,
because 302.6 contains none of the question's words. It says "under its
controller's control continuously since their most recent turn began" and then
calls that the "summoning sickness" rule -- a phrase nobody learning the game
has ever heard.

Two halves here: that the map fires on what a person would actually type, and
that it does not fire on anything else. The second matters more -- every entry
decides what a question is about before seeing the question, so a pattern that
is too eager makes retrieval worse for questions it was never meant to touch.
"""

from __future__ import annotations

import pytest

from helpers_rules import PASSAGES
from mtgcoach.rules.phrasing import LIFE_TOTAL, SUMMONING_SICKNESS, TARGETS, also
from mtgcoach.rules.terms import query


@pytest.mark.parametrize(
    "question",
    [
        "can a creature that came into play this turn block?",
        "Can a creature that comes into play this turn attack?",
        "can I attack with a creature I just played?",
        "can he attack with the goblin he just cast?",
        "is the ogre I only just summoned allowed to attack",
        "can it attack if I played it this turn?",
        "can I attack with a creature that entered the battlefield this turn?",
        "can a new creature attack",
        "does a brand-new creature have to wait",
        "can a brand new creature block",
    ],
)
def test_the_ways_somebody_asks_about_a_creature_that_only_just_arrived(question: str) -> None:
    """Nobody types the phrase that finds rule 302.6.

    A child says "just played"; a parent who last played in 1998 says "came
    into play".
    """
    assert SUMMONING_SICKNESS in also(question), question


@pytest.mark.parametrize(
    "question",
    [
        "how does trample work when blocked?",
        "what does deathtouch do?",
        "can a tapped creature block?",
        "when does a creature come back from the graveyard?",
        "how many cards do I play at the start?",
        "what is the play order in a multiplayer game?",
        "can I block with two creatures?",
        "does a creature that attacked stay tapped this turn?",
    ],
)
def test_a_question_the_rules_already_share_words_with_is_left_alone(question: str) -> None:
    """These find their rules on their own.

    Adding a phrase to them would put an unrelated passage in the prompt and
    push a relevant one out -- the retrieval limit is eight.
    """
    assert also(question) == (), question


def test_the_old_wording_also_asks_about_entering() -> None:
    """The pre-2009 wording for entering the battlefield.

    Somebody asking what happens when a creature comes into play wants the
    rules about the event, not only the restriction on a new one -- so both
    phrases are added.
    """
    assert also("what happens when a creature comes into play?") == (
        SUMMONING_SICKNESS,
        "entered the battlefield",
    )


def test_a_child_says_hit_points_and_the_rules_never_do() -> None:
    assert also("what happens when my hit points reach zero?") == (LIFE_TOTAL,)


def test_a_phrase_is_added_once_however_many_entries_match() -> None:
    """Two entries name summoning sickness for the same question."""
    added = also("can a creature that came into play this turn and was just cast attack?")
    assert added.count(SUMMONING_SICKNESS) == 1


def test_every_phrase_this_can_add_is_really_in_the_rules() -> None:
    """A target the document does not contain adds nothing to a query but noise.

    Here against the excerpt, which carries a real passage for each of them --
    302.6 and the glossary entry for summoning sickness, 110.2 for entering,
    119.1 for a life total. And against the *installed* Comprehensive Rules by
    `tools/check_rules_phrasing.py`, because the excerpt is only what these
    tests needed and the document is what a question is actually searched in.
    """
    corpus = "\n".join(f"{passage.title}\n{passage.text}" for passage in PASSAGES).lower()
    assert [target for target in sorted(TARGETS) if target not in corpus] == []


def test_the_added_phrase_reaches_the_query_as_a_phrase() -> None:
    """Quoted, so FTS5 matches the words together.

    Unquoted it would be two more ORed words -- "summoning" and "sickness" --
    and "sickness" appears in the rules only inside the phrase anyway, so the
    quotes cost nothing and say what is meant.
    """
    assert '"summoning sickness"' in query("can a creature that just came into play block?")


@pytest.mark.parametrize("question", ["what?", "can it?", "is it?", "do I?"])
def test_a_question_with_nothing_searchable_in_it_stays_an_empty_query(question: str) -> None:
    """An empty query means "the rules cannot be looked up for this".

    The map must not be able to turn one into a lookup, and it cannot: every
    phrase needs a trigger word that is not noise -- "play", "cast",
    "creature". A query built only from a guess would be a guess with nothing
    to check it.
    """
    assert query(question) == ""
    assert also(question) == ()


@pytest.mark.parametrize(
    "question",
    [
        "can a creature that came into play this turn block?",
        "can I attack with a creature I just played?",
        "what happens when my hit points reach zero?",
    ],
)
def test_an_added_phrase_never_stands_alone_in_a_query(question: str) -> None:
    """The question's own words are always in there too.

    A query that was only the map's guess would retrieve on a paraphrase the
    person did not confirm, and the passages are shown under the answer -- so
    they have to be the ones the question asked for.
    """
    built = query(question)
    for phrase in also(question):
        built = built.replace(f'"{phrase}"', "")
    assert built.strip(" OR") != "", question
