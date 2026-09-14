"""When a word that is a Magic keyword is just an ordinary English word.

Magic names its abilities with real words -- reach, flying, haste, trample,
menace, shadow, fear -- and there are a hundred and sixty of them in one word
each. So a question can contain one without being about it, and full-text
search cannot tell the difference. Found live:

    what happens when my hit points reach zero?

"Reach" appears seventeen times in the whole document, nearly all of them the
keyword, which makes it *rare* -- so bm25 weights it heavily, and the four
passages titled "Reach" took the top of the results. The rule the question
wanted, that a player at 0 life loses, was nowhere.

**Which way to be wrong.** A question about a keyword is far commoner than a
question that merely contains one, and dropping the wrong word is much worse
than keeping it: "what about deathtouch?" with "deathtouch" dropped retrieves
nothing at all. So the keyword reading is the default and stays the default,
and a word is set aside only on one narrow signal -- a number *word* straight
after it, as in "reach zero" or "reach twenty". A keyword is a noun; a number
after it makes it a verb with an object.

Three things are deliberately *not* signals, each because a review found the
question it breaks:

- **A digit.** "Toxic 1", "Ward 2", "Discover 5": seventy of the hundred and
  sixty keywords take a number, cards write it as a digit, and so does anybody
  quoting one. "What does toxic 1 do?" lost its only searchable word and
  retrieved nothing. A person writing English writes "zero", not "0".
- **A subject pronoun before it.** "Does it trample?" and "can it exploit?" are
  questions about the ability, and both came out as an empty query -- "does"
  and "it" are noise words, so setting the keyword aside left nothing at all,
  and an empty query means "the rules cannot be looked up for this". It also
  bought nothing: every question it was written for is caught by the number
  word anyway.
- **Anything at all, if it would empty the query.** Kept as a backstop even
  though no signal should now be able to: a collision that ranks the wrong
  passage is a worse answer, but no query is no answer.

Inflections count. The index is porter-stemmed, so "reaches" in a question
matches every passage titled Reach -- which means "my life reaches zero" had
exactly the collision this module exists to prevent, and the module did not
notice, because it compared the surface word against the heading.

**The list of keywords comes from the document, not from here.** There are 160
and Wizards add several a year, so a list written out in this file would be
wrong by the next set -- and this project has to work on sets nobody has
printed yet. ``names_in`` reads them off the 702.x passages, which is where the
rules define them.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterable

    from mtgcoach.rules.corpus import Passage

#: Where the Comprehensive Rules define keyword abilities. One per ``702.N``,
#: with the ability's name as the heading.
_KEYWORD_RULE = re.compile(r"^702\.\d")

#: Numbers as a person writes them. The rules write digits, so a number word
#: after a keyword is a strong sign the sentence is English rather than Magic.
NUMBERS = frozenset(
    [
        "zero",
        "one",
        "two",
        "three",
        "four",
        "five",
        "six",
        "seven",
        "eight",
        "nine",
        "ten",
        "eleven",
        "twelve",
        "thirteen",
        "fourteen",
        "fifteen",
        "sixteen",
        "seventeen",
        "eighteen",
        "nineteen",
        "twenty",
        "thirty",
        "forty",
        "fifty",
    ]
)

#: A word, as ``terms`` cuts them, so both agree on what a word is.
_WORD = re.compile(r"[a-z0-9]+(?:['\u2019][a-z]+)?")


def names_in(passages: Iterable[Passage]) -> frozenset[str]:
    """Every one-word keyword ability the rules define, lowercased.

    One word only. A keyword written as two -- "first strike", "double strike"
    -- cannot be mistaken for ordinary English in a question, because nobody
    writes those words together by accident, and the phrase is what makes the
    rule findable.
    """
    return frozenset(
        passage.title.strip().lower()
        for passage in passages
        if _KEYWORD_RULE.match(passage.reference)
        and passage.title.strip()
        and " " not in passage.title.strip()
    )


#: Endings the porter stemmer in the index collapses, shortest last so the
#: longest match is tried first. Not a stemmer: enough to recognise that
#: "reaches" is the word "reach", which is all this has to decide.
_ENDINGS = ("ing", "es", "ed", "s", "d")


def ordinary(question: str, keywords: frozenset[str]) -> frozenset[str]:
    """The keyword words this question uses as plain English, if any.

    Returns the words *as the question spelled them*, so the caller can drop
    exactly those -- "reaches", not "reach".

    Empty for almost every question, which is the point: this only fires on
    evidence, and the evidence is deliberately hard to produce by accident.
    """
    words = _WORD.findall(question.lower())
    return frozenset(
        word
        for index, word in enumerate(words)
        if _names_a_keyword(word, keywords) and _is_verb(words, index)
    )


def _names_a_keyword(word: str, keywords: frozenset[str]) -> bool:
    """Whether this word is a keyword's name, in any inflection.

    The index is porter-stemmed, so "reaches" matches every passage titled
    Reach -- and comparing the surface word against the heading missed exactly
    that, leaving "my life reaches zero" with the collision this module exists
    to prevent.
    """
    if word in keywords:
        return True
    return any(word.endswith(ending) and word[: -len(ending)] in keywords for ending in _ENDINGS)


def _is_verb(words: list[str], index: int) -> bool:
    """Whether the word at ``index`` is being used as a verb.

    One signal, and the module docstring says what the rejected ones cost.
    Widening this is how the check starts dropping words from questions that
    were about the keyword all along, so anything added here wants a
    measurement behind it -- ``tools/check_retrieval.py`` is that measurement.
    """
    after = words[index + 1] if index + 1 < len(words) else ""
    return after in NUMBERS
