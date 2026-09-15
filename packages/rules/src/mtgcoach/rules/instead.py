"""The one case where a paraphrase *replaces* a word rather than adding to it.

``phrasing`` supplies the rules' own wording for something a question says in
other words, and appends it: the question's words and the rules' words compete
on bm25 and the better evidence wins. That is right for every entry but one.

"Die" does not compete -- it wins, for the wrong rule. The document's only uses
of the term are the planar die and the heading of rule 706, "Rolling a Die",
and a heading outranks a phrase. So "when does my creature die from damage?"
returned eight passages, every one of them about dice, and rule 700.4 -- which
defines the word -- was not among them.

Its own module rather than a field on ``PHRASES``, because the exception should
be as visible as it is rare. A list of words to ignore is a stop list, a stop
list grows, and a stop list that grows starts deciding what a question is
about.
"""

from __future__ import annotations

import re

#: Words a matched paraphrase makes *misleading*, to be set aside rather than
#: searched for.
#:
#: The exception to "this adds, it never replaces", and it needed one. Every
#: other entry supplies wording the question lacked and competes fairly with
#: the question's own words. "Die" does not compete -- it wins, for the wrong
#: rule. The document's only uses of the term are the planar die and the
#: heading of rule 706, "Rolling a Die", and a heading outranks a phrase; so
#: "when does my creature die from damage?" returned eight passages, all of
#: them about dice, and the one that defines the word was not among them.
#:
#: Kept to the one case that earns it. A list of words to ignore is a stop
#: list, a stop list grows, and a stop list that grows starts deciding what a
#: question is about.
INSTEAD: tuple[tuple[re.Pattern[str], frozenset[str]], ...] = (
    (
        re.compile(
            r"(?=.*\b(?:creature|creatures|guy|guys|bear|damage|combat|toughness)\b)"
            r".*\b(?:dies?|died|dying|dead|death)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        frozenset({"die", "dies", "died", "dying", "dead", "death"}),
    ),
)


def instead_of(question: str) -> frozenset[str]:
    """Words this question's paraphrases replace rather than add to.

    Empty for almost every question. See ``INSTEAD``.
    """
    found: set[str] = set()
    for pattern, words in INSTEAD:
        if pattern.search(question):
            found |= words
    return frozenset(found)
