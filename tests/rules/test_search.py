"""Finding the rules a question is about.

Retrieval is allowed to be approximate -- what it returns goes into a prompt
and the model reads all of it. What it is not allowed to do is let a question
reach FTS5 as syntax, or return nothing for a question that is plainly about
trample.
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

import pytest

from helpers_rules import PASSAGES
from mtgcoach.rules.search import RuleIndex
from mtgcoach.rules.terms import query

if TYPE_CHECKING:
    from collections.abc import Generator


@pytest.fixture(scope="module")
def index() -> Generator[RuleIndex]:
    """The excerpt, indexed once for the module."""
    with RuleIndex.build(PASSAGES) as built:
        yield built


def _references(index: RuleIndex, question: str, limit: int = 8) -> list[str]:
    return [passage.reference for passage in index.search(question, limit)]


def test_a_question_finds_the_rule_it_is_about(index: RuleIndex) -> None:
    assert "702.19b" in _references(index, "how does trample work when blocked?")


def test_the_heading_outranks_a_passing_mention(index: RuleIndex) -> None:
    """A question about deathtouch wants the deathtouch rules first."""
    found = _references(index, "what does deathtouch do?", limit=3)
    assert all(reference.startswith(("702.2", "Deathtouch")) for reference in found), found


def test_a_question_about_blocking_finds_the_blocking_step(index: RuleIndex) -> None:
    assert any(r.startswith("509") for r in _references(index, "who chooses the blockers?"))


def test_the_limit_is_honoured(index: RuleIndex) -> None:
    assert len(_references(index, "creature damage rule", limit=2)) == 2


def test_a_question_of_only_noise_finds_nothing(index: RuleIndex) -> None:
    """Better than the eight highest-ranked passages for no question at all."""
    assert _references(index, "what is it?") == []


def test_an_empty_question_finds_nothing(index: RuleIndex) -> None:
    assert _references(index, "") == []


def test_punctuation_cannot_reach_the_search_as_syntax(index: RuleIndex) -> None:
    """FTS5 would choke on a bare quote, or read NOT/OR as operators."""
    assert _references(index, 'trample" OR NOT (x') == _references(index, "trample")


def test_a_word_nothing_matches_finds_nothing(index: RuleIndex) -> None:
    assert _references(index, "zzzyzzx") == []


def test_a_citation_is_looked_up_exactly(index: RuleIndex) -> None:
    (found,) = index.cited(["702.19b"])
    assert found.title == "Trample"


def test_citations_come_back_in_the_order_asked_for(index: RuleIndex) -> None:
    assert [p.reference for p in index.cited(["Trample", "100.1"])] == ["Trample", "100.1"]


def test_a_citation_that_is_not_there_is_simply_absent(index: RuleIndex) -> None:
    """The caller is checking whether it exists; a near-miss would defeat that."""
    assert [p.reference for p in index.cited(["702.19b", "999.9z"])] == ["702.19b"]


def test_an_index_can_be_closed_twice_over() -> None:
    """The context manager closes it; closing again must not raise."""
    built = RuleIndex.build(PASSAGES)
    with built:
        assert built.search("trample")
    built.close()


# --- turning a question into search terms -------------------------------------


def test_words_are_ored_not_anded() -> None:
    """One word spelled differently from the rules must not lose the rest."""
    assert query("trample blocking") == '"trample" OR "blocking"'


def test_noise_words_are_dropped() -> None:
    assert query("how does the trample work") == '"trample" OR "work"'


def test_single_letters_are_dropped() -> None:
    """A stray "a" or an initial ranks nothing and matches everything."""
    assert query("x trample") == '"trample"'


def test_an_apostrophe_stays_inside_a_word() -> None:
    assert query("player's turn") == '"player\'s" OR "turn"'


def test_quotes_and_operators_become_words_or_nothing() -> None:
    """FTS5 operators are English words, and English words are noise here."""
    assert query('"trample" AND NOT flying') == '"trample" OR "flying"'


def test_the_index_can_be_searched_from_another_thread(index: RuleIndex) -> None:
    """The rules route is a plain `def`, so FastAPI runs it in a worker thread.

    A connection made on the main thread raised ProgrammingError on every
    question -- found by the route tests, pinned here where the cause is.
    """
    found: list[list[str]] = []
    worker = threading.Thread(target=lambda: found.append(_references(index, "trample")))
    worker.start()
    worker.join()
    assert found == [_references(index, "trample")]
