"""When a word that is a Magic keyword is just an ordinary English word.

Magic names its abilities with real words -- reach, flying, haste, trample,
menace, shadow, fear -- a hundred and sixty of them in one word each. So a
question can contain one without being about it, and full-text search cannot
tell. Found live: *what happens when my hit points reach zero?* "Reach" appears
seventeen times in the whole document, nearly all the keyword, which makes it
*rare* -- so bm25 weighted it heavily, the four passages titled "Reach" took
the top of the results, and the rule the question wanted was nowhere.

**Which way to be wrong.** A question about a keyword is far commoner than a
question that merely contains one, and dropping the wrong word is much worse
than keeping it: "what about deathtouch?" with "deathtouch" dropped retrieves
nothing at all. So the keyword reading is the default and stays the default,
and a word is set aside only on one narrow signal -- a number *word* straight
after it, as in "reach zero" or "reach twenty". A keyword is a noun; a number
after it makes it a verb with an object.

Three things are deliberately *not* signals, each because a review found the
question it breaks:

- **A number after a keyword that takes one.** "Toxic 1", "Ward 2", "Crew 3":
  seventy of the hundred and sixty keywords are written with a parameter, so a
  number after one of *those* is the parameter rather than an object. "What
  does toxic 1 do?" lost its only searchable word and retrieved nothing;
  excluding digits alone fixed that spelling and left "what does toxic one
  do?" broken. Which keywords take a number is read off the rules, like the
  names -- ``Ward [cost]``, ``"toxic N"``, ``"Crew N"``.
- **A subject pronoun before it.** "Does it trample?" and "can it exploit?" are
  questions about the ability, and both came out as an empty query -- "does"
  and "it" are noise, so setting the keyword aside left nothing, and an empty
  query means "the rules cannot be looked up for this". It bought nothing the
  number word does not.
- **Anything at all, if it would empty the query.** A backstop, in ``terms``:
  a collision ranks the wrong passage, but no query ranks none.

Inflections count: the index is porter-stemmed, so "reaches" matches every
passage titled Reach, and comparing the surface word against the heading meant
"my life reaches zero" kept the very collision this exists to prevent.

**The list of keywords comes from the document, not from here.** There are 160
and Wizards add several a year, so a list written out in this file would be
wrong by the next set -- and this project has to work on sets nobody has
printed yet. ``names_in`` reads them off the 702.x passages, which is where the
rules define them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class Keywords:
    """What a document calls its abilities, and which of them take a number.

    One object rather than two arguments threaded side by side: they are read
    off the same passages, they are always used together, and a caller that
    had one and not the other would be wrong in a way nothing would catch.
    """

    #: Every one-word ability name, lowercased.
    names: frozenset[str] = frozenset()
    #: The subset written with a parameter -- ``Ward [cost]``, ``"toxic N"``.
    numbered: frozenset[str] = frozenset()


#: No document, so nothing is ever set aside. What a caller that does not have
#: an index gets, and what this behaved like before any of it existed.
NONE = Keywords()

#: How the rules write a keyword that takes one: the name, then ``N``, ``X``,
#: a bracketed cost, or a digit.
_PARAMETER = r"\s*(?:[NX]\b|\[|\d)"


def keywords_in(passages: Iterable[Passage]) -> Keywords:
    """The ability names this document defines, and which take a number.

    One word only. A keyword written as two -- "first strike", "double strike"
    -- cannot be mistaken for ordinary English in a question, because nobody
    writes those words together by accident, and the phrase is what makes the
    rule findable.
    """
    bodies: dict[str, list[str]] = {}
    for passage in passages:
        name = passage.title.strip().lower()
        if _KEYWORD_RULE.match(passage.reference) and name and " " not in name:
            bodies.setdefault(name, []).append(passage.text)
    return Keywords(
        names=frozenset(bodies),
        numbered=frozenset(name for name, text in bodies.items() if _takes_a_number(name, text)),
    )


def _takes_a_number(name: str, body: list[str]) -> bool:
    """Whether the rules write this keyword with a parameter."""
    written = re.compile(re.escape(name) + _PARAMETER, re.IGNORECASE)
    return any(written.search(text) for text in body)


#: Endings the porter stemmer in the index collapses, shortest last so the
#: longest match is tried first. Not a stemmer: enough to recognise that
#: "reaches" is the word "reach", which is all this has to decide.
_ENDINGS = ("ing", "es", "ed", "s", "d")


def ordinary(question: str, keywords: Keywords) -> frozenset[str]:
    """The keyword words this question uses as plain English, if any.

    Returns the words *as the question spelled them* -- "reaches", not "reach"
    -- so the caller can drop exactly those. Empty for almost every question,
    which is the point: the evidence is hard to produce by accident.
    """
    words = _WORD.findall(question.lower())
    return frozenset(
        word
        for index, word in enumerate(words)
        if _named(word, keywords.names) and _is_verb(word, words, index, keywords)
    )


def _named(word: str, names: frozenset[str]) -> str:
    """The keyword this word names, in any inflection, or empty.

    The index is porter-stemmed, so "reaches" matches every passage titled
    Reach -- and comparing the surface word against the heading missed exactly
    that, leaving "my life reaches zero" with the collision this module exists
    to prevent.
    """
    if word in names:
        return word
    for ending in _ENDINGS:
        root = word[: -len(ending)]
        if word.endswith(ending) and root in names:
            return root
    return ""


def _is_verb(word: str, words: list[str], index: int, keywords: Keywords) -> bool:
    """Whether the word at ``index`` is being used as a verb.

    One signal, and the module docstring says what the rejected ones cost.
    Widening this is how the check starts dropping words from questions that
    were about the keyword all along, so anything added here wants a
    measurement behind it -- ``tools/check_retrieval.py`` is that measurement.
    """
    after = words[index + 1] if index + 1 < len(words) else ""
    if after not in NUMBERS:
        return False
    # A number after a keyword that is *written* with one is its parameter.
    # "What does toxic one do?" is a question about toxic, not a sentence in
    # which somebody toxics a number.
    return _named(word, keywords.names) not in keywords.numbered
