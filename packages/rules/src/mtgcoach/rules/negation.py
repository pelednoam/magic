"""When the question and the rule say the same thing in opposite polarity.

The rules state restrictions as requirements. A question states the thing being
restricted. So the two describe one fact with opposite signs, and share no word
at all:

    can a tapped creature block?          509.1a: "must be untapped"
    what if nobody blocks my creature?    510.1b: "an unblocked creature"

Stemming does not help and cannot: "tapped" stems to ``tap`` and "untapped" to
``untap``, which is right -- they are opposites, and a search engine that
conflated them would answer "can a tapped creature block" with "yes". The
words genuinely differ. What is missing is the *bridge*, and the bridge is a
fact about English, not about ranking.

Kept apart from ``phrasing`` because it is a different problem. That module
handles a beginner having no word for a concept; this one handles a beginner
having exactly the right word and the rules having written its opposite. The
mechanism is the same -- a pattern, and the words to add -- so both feed
``terms.query``, and both are checked against the installed document by
``tools/check_rules_phrasing.py``.

**Narrow on purpose, and measured.** Each entry below turned a question that
retrieved nothing useful into one that retrieves the answering rule first or
second, with no other question's results changed --
``tools/check_retrieval.py`` is where that is kept true. A wider rule is easy
to write and hard to keep honest: "not X" -> "unX" applied blindly turns "not
less than" into a search for "unless", which is a word the rules use
eighty-seven times and never as a negation of "less".
"""

from __future__ import annotations

import re

#: What 508.1a and 509.1a say, and the only two places the phrase appears in
#: the whole document -- so it is about as specific a thing to search for as
#: exists. Both are the answer to "can a tapped creature attack/block".
MUST_BE_UNTAPPED = "must be untapped"

#: What the rules call a creature nobody blocked. A person says "not blocked"
#: or "nobody blocked it".
#:
#: The whole phrase, not the bare word: "unblocked" alone is the *title* of two
#: glossary entries, and a title match is weighted four times a body one, so
#: the two definitions took the top of the list and 510.1b -- the rule that
#: says what actually happens -- was not in the top eight at all.
UNBLOCKED = "unblocked creature"

#: And what happens to one. A question asking "what happens if nobody blocks
#: my creature?" is asking about damage and never says the word, so without
#: this the glossary answered "what is an unblocked creature" instead of the
#: question, and the answerer refused for want of a rule to cite. Verified
#: live, and it is why the entry adds two phrases rather than one.
COMBAT_DAMAGE = "combat damage"

#: Both apostrophes. A phone substitutes the typographic one (U+2019) by
#: default, and the client here *is* a phone app -- so a pattern matching only
#: the straight one silently never fires for the person it was written for.
_APOSTROPHE = "['\u2019]?"

#: Each entry: a question's polarity, and the rules' word for the other one.
#:
#: Note ``\btapped\b`` does not match inside "untapped" -- there is no word
#: boundary between "un" and "tapped" -- so a question already using the rules'
#: word is left alone rather than having its own word added back.
PAIRS: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    # A tapped creature, asked about attacking or blocking. Both halves are
    # required: "what does tapped mean?" wants the glossary, not the combat
    # restriction, and adding the phrase there would push the glossary out.
    (
        re.compile(
            r"(?=.*\btapped\b)(?=.*\b(?:attacks?|attacked|attacking|attacker"
            r"|blocks?|blocked|blocking|blocker)\b)",
            re.IGNORECASE | re.DOTALL,
        ),
        (MUST_BE_UNTAPPED,),
    ),
    # Nobody blocked it. The rules have one word for this and a person has
    # three.
    #
    # Every alternative here is a *negation*. The first version listed bare
    # "is" and "was" among them, so "what happens when my creature is
    # blocked?" -- a first-game question at least as common as its negative
    # twin -- was steered to the rules for the opposite game state. Two
    # reviewers found it independently.
    (
        re.compile(
            rf"\b(?:"
            rf"(?:is|was|are|were|does|did|do|has|have|ca|could|would)n{_APOSTROPHE}t"
            rf"\s+(?:get\s+|been\s+)?blocked"
            rf"|(?:is|was|are|were)\s+(?:not|never)\s+blocked"
            rf"|(?:not|never)\s+blocked"
            rf"|no(?:body|\s*one|thing)\s+block(?:s|ed)?"
            rf"|without\s+(?:being\s+)?blocked"
            rf")\b",
            re.IGNORECASE,
        ),
        (UNBLOCKED, COMBAT_DAMAGE),
    ),
)

#: Every phrase this module can add, for the check that keeps them real.
TARGETS = frozenset(target for _pattern, targets in PAIRS for target in targets)


def spelled_out(question: str) -> tuple[str, ...]:
    """The rules' words for anything this question puts the other way round.

    In ``PAIRS`` order and without repeats, so a question matching two entries
    adds each phrase once.
    """
    found = [target for pattern, targets in PAIRS if pattern.search(question) for target in targets]
    return tuple(dict.fromkeys(found))
