"""Turning a question somebody typed into something FTS5 will accept.

Kept apart from the search itself because it is the only part with an opinion
in it. Everything else is a lookup; this decides what a question is *about*,
and getting it wrong means the right rule is never retrieved and the model is
left answering from memory -- which is the failure this whole package exists to
prevent.
"""

from __future__ import annotations

import re

#: A word worth searching for. Apostrophes are kept inside a word ("player's")
#: and everything else is a separator, which also means nothing a person types
#: can reach FTS5 as syntax.
_WORD = re.compile(r"[A-Za-z0-9]+(?:'[A-Za-z]+)?")

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


def query(question: str) -> str:
    """A question, as an FTS5 query.

    Built from extracted words rather than escaped, which is the difference
    between "safe as long as nobody types a quote" and "cannot carry syntax at
    all". Words are ORed: a question is a bag of terms, and requiring all of
    them finds nothing as soon as one is spelled differently from the rules.
    """
    words = [word.lower() for word in _WORD.findall(question)]
    wanted = [word for word in words if word not in _NOISE and len(word) > 1]
    return " OR ".join(f'"{word}"' for word in wanted)
