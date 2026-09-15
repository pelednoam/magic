"""Which revision of the Comprehensive Rules is installed.

The document says so itself, on its third line, and that sentence is what a
game records as the rules it was played under and what a rules scenario records
as the document it was derived from -- items 5 and 8 of the decisions.

Read out of the *text* rather than from the URL it was downloaded from,
because the URL is not in the file: an operator who renamed the download has
lost it, and the sentence travels with the copy actually being quoted.
"""

from __future__ import annotations

import pytest

from helpers_rules import REVISION
from mtgcoach.rules.effective import UNKNOWN, effective_from

#: The real document's opening, as of the copy CI fetches.
REAL = (
    "Magic: The Gathering Comprehensive Rules\n"
    "\n"
    "These rules are effective as of August 7, 2026.\n"
    "\n"
    "Introduction\n"
)


def test_the_revision_is_read_off_the_document() -> None:
    assert effective_from(REAL) == "August 7, 2026"


def test_a_document_that_does_not_say_is_recorded_as_not_saying() -> None:
    """Empty rather than a guess.

    "We do not know which revision this was" is a fact worth keeping; a
    plausible-looking date nobody read off the file is not.
    """
    assert effective_from("Magic: The Gathering Comprehensive Rules\n") == UNKNOWN


@pytest.mark.parametrize(
    "when",
    ["August 7, 2026", "1 August 2026", "2026-08-07"],
)
def test_the_date_format_is_wizards_to_change(when: str) -> None:
    """Carried as the document's own words, not parsed into a date.

    A `date` would need a format, a locale, and a decision about what to do
    with a line that does not match -- and every use of this is comparison or
    display, neither of which is helped by having thrown the original away.
    """
    assert effective_from(f"These rules are effective as of {when}.") == when


def test_the_line_has_to_be_the_line() -> None:
    """A rule that mentions the phrase mid-sentence is not the revision."""
    assert effective_from("See the note about when these rules are effective as of a date.") == (
        UNKNOWN
    )


def test_the_first_answer_wins() -> None:
    """An excerpt that quotes the phrase twice is still one document."""
    twice = "These rules are effective as of August 7, 2026.\nThese rules are effective as of X.\n"
    assert effective_from(twice) == "August 7, 2026"


def test_the_excerpt_every_rules_test_uses_says_which_revision_it_is() -> None:
    """Item 8: each rules scenario records the document it was derived from.

    Every expectation in `tests/rules` comes from this one excerpt, so this is
    that record -- and it is an assertion rather than a comment because a
    fixture re-cut from a newer document has to move the date with it. An
    excerpt that had lost the line would record nothing while every scenario
    went on claiming the authority of the rules.
    """
    assert REVISION == "February 7, 2025"
