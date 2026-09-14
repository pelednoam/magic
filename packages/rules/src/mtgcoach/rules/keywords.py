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
and a word is set aside only on *positive* evidence that it is being used as an
ordinary verb:

- something countable straight after it -- "reach zero", "reach 20". A keyword
  is a noun; a number after it makes it a verb with an object.
- a subject pronoun straight before it -- "I reach", "it reaches".

Both are narrow on purpose. "The defender blocks" is not demoted, because "the
defender" could be either and the question has "blocks" to find the rule with
anyway; measured, it retrieves the right rule either way.

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

#: Pronouns that make the next word a verb. "I reach", "it reaches".
SUBJECTS = frozenset(
    ["i", "we", "you", "they", "it", "he", "she", "who", "nobody", "everyone", "someone"]
)

#: A word, as ``terms`` cuts them, so both agree on what a word is.
_WORD = re.compile(r"[a-z0-9]+(?:'[a-z]+)?")


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


def ordinary(question: str, keywords: frozenset[str]) -> frozenset[str]:
    """The keyword words this question uses as plain English, if any.

    Empty for almost every question, which is the point: this only fires on
    evidence, and the evidence is deliberately hard to produce by accident.
    """
    words = _WORD.findall(question.lower())
    return frozenset(
        word for index, word in enumerate(words) if word in keywords and _is_verb(words, index)
    )


def _is_verb(words: list[str], index: int) -> bool:
    """Whether the word at ``index`` is being used as a verb.

    Only the two signals in the module docstring. Widening this is how the
    check starts dropping words from questions that were about the keyword all
    along, so anything added here wants a measurement behind it --
    ``tools/check_retrieval.py`` is where that measurement lives.
    """
    before = words[index - 1] if index else ""
    after = words[index + 1] if index + 1 < len(words) else ""
    return after in NUMBERS or after.isdigit() or before in SUBJECTS
