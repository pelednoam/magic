"""Turning a question somebody typed into something FTS5 will accept.

Kept apart from the search itself because it is the only part with an opinion
in it. Everything else is a lookup; this decides what a question is *about*,
and getting it wrong means the right rule is never retrieved and the model is
left answering from memory -- which is the failure this whole package exists to
prevent.
"""

from __future__ import annotations

import re

from mtgcoach.rules import negation, phrasing
from mtgcoach.rules.keywords import ordinary

#: A word worth searching for. Apostrophes are kept inside a word ("player's")
#: and everything else is a separator, which also means nothing a person types
#: can reach FTS5 as syntax.
_WORD = re.compile(r"[A-Za-z0-9]+(?:['\u2019][A-Za-z]+)?")

#: Words that match most of the document and so rank nothing. Deliberately
#: short: a stop list that grows starts deciding what a question is about.
_NOISE = frozenset(
    [
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "but",
        "by",
        "can",
        "do",
        "does",
        "for",
        "from",
        "has",
        "have",
        "how",
        "i",
        "if",
        "in",
        "is",
        "it",
        "my",
        "no",
        "not",
        "of",
        "on",
        "or",
        "should",
        "that",
        "the",
        "their",
        "them",
        "then",
        "there",
        "these",
        "this",
        "to",
        "was",
        "what",
        "when",
        "where",
        "which",
        "who",
        "why",
        "will",
        "with",
        "you",
        "your",
    ]
)


def query(question: str, keywords: frozenset[str] = frozenset()) -> str:
    """A question, as an FTS5 query.

    Built from extracted words rather than escaped, which is the difference
    between "safe as long as nobody types a quote" and "cannot carry syntax at
    all". Words are ORed: a question is a bag of terms, and requiring all of
    them finds nothing as soon as one is spelled differently from the rules.

    Plus whatever ``phrasing`` and ``negation`` can add -- a paraphrase turned
    into the rules' phrase for it, and a polarity turned into the rules'
    opposite one. Those are multi-word phrases rather than words, which FTS5
    reads as phrase matches, and that is what is wanted: a question that shares
    no word with its rule gets the rule's own wording added to the bag so the
    passage can rank at all.

    Appended, never substituted, so this only ever adds a way to match. It also
    cannot turn an empty query into a non-empty one: every phrase in the map
    needs a word to trigger on that is not in ``_NOISE`` -- "play", "cast",
    "creature" -- so a question with nothing searchable in it triggers nothing
    either. ``search`` depends on that: an empty query means "the rules cannot
    be looked up for this", and a query built only from a guess would be a
    guess with nothing to check it.

    Minus anything ``keywords`` says is a Magic keyword being used as ordinary
    English. Those are dropped rather than down-weighted: a keyword name is
    rare in the document and so scores heavily, and the document has no other
    use for the word, so keeping it can only pull the wrong passages up. The
    names come from the index, which read them off the rules -- see
    ``keywords.names_in``. Empty by default, which is no change at all.
    """
    words = [word.lower() for word in _WORD.findall(question)]
    searchable = [word for word in words if word not in _NOISE and len(word) > 1]
    english = ordinary(question, keywords)
    wanted = [word for word in searchable if word not in english]
    if not wanted:
        # Setting words aside may not leave nothing. "Does it trample?" is
        # three words, two of them noise, so dropping the keyword left an empty
        # query -- which `search` reads as "the rules cannot be looked up for
        # this" and answers with no passages at all. A collision ranks the
        # wrong passage; this ranks none.
        wanted = searchable
    added = (*phrasing.also(question), *negation.spelled_out(question))
    return " OR ".join(f'"{term}"' for term in (*wanted, *added))


#: Every phrase ``query`` can add, from either map. One name for the lot, so
#: ``tools/check_rules_phrasing.py`` has a single thing to check and a third
#: map later changes one line rather than two files.
TARGETS = phrasing.TARGETS | negation.TARGETS

#: A rule number written out in a question: "702.19b", "rule 100.1", "509.1a".
#: Three digits and a dot are what make it unambiguous -- a bare "19b" is not a
#: rule number, and a year is not either.
_REFERENCE = re.compile(r"\b(\d{3}\.\d+[a-z]?)\b", re.IGNORECASE)


def references_in(question: str) -> tuple[str, ...]:
    """Every rule number the question names, in the order it names them.

    A question that says which rule it is about is the one case where retrieval
    can be exact instead of ranked, and it is a common one: somebody reading a
    card's reminder text asks what 702.19b says. Full-text search handled that
    badly -- the number tokenises to "702" and "19b", and the rule itself
    ranked nowhere in particular among everything else mentioning 702.
    """
    # Lowered, because the index stores them lowered-by-convention -- the
    # document writes "702.19b" and somebody typing "702.19B" means the same
    # rule.
    return tuple(dict.fromkeys(found.lower() for found in _REFERENCE.findall(question)))
