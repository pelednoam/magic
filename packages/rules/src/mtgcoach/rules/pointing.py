"""The passages a question's own paraphrases point at.

A phrase in ``phrasing`` is chosen because it is the rules' *own* wording for
what the question asks, so a match on it is far better evidence than a match on
"cast" or "creature". In an OR query of common words it loses anyway: bm25
normalises by length, and the rules that answer a beginner's question are long.
"Can I cast Giant Growth without a creature?" put the phrase for CR 601.2c in
the query, matched it, and ranked it ninth of eight.

So a couple of slots are reserved, the way ``search`` already reserves them for
a rule the question names by number. Split from ``search`` at the line limit,
and it takes the matcher as an argument rather than reaching for a connection:
this is a ranking decision, not a database one.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.rules.phrasing import also

if TYPE_CHECKING:
    from collections.abc import Callable

    from mtgcoach.rules.corpus import Passage

#: How to run one FTS5 query. ``RuleIndex._matching``, passed in -- this is a
#: ranking decision, not a database one, so the database is an argument.
#:
#: A PEP 695 alias, so the right-hand side is evaluated lazily and the names in
#: it can stay inside the type-checking block.
type Matcher = Callable[[str, int], tuple[Passage, ...]]

#: How many passages a paraphrase may reserve. Two, because a question rarely
#: matches more than one entry in the map and the second is there for the one
#: that does -- "when does my creature die" wants both the definition and the
#: reason. More would start answering the map's question instead of the
#: player's.
RESERVED = 2


def pointed_at(matching: Matcher, question: str, limit: int, taken: int) -> tuple[Passage, ...]:
    """The best passages the question's paraphrases point at, if any.

    At most ``RESERVED`` of them, and never more than half the answer.
    The phrases are good evidence and they are not the whole question: a
    reserved slot that crowded out the ranked results would trade one
    retrieval failure for another.
    """
    phrases = also(question)
    if not phrases:
        return ()
    room = min(RESERVED, max(0, limit // 2 - taken))
    if room <= 0:
        return ()
    # One query per phrase, best hit from each, rather than one OR of all
    # of them. The map lists its phrases most-precise-first, and an OR
    # throws that away: "legal target" occurs twenty-six times and "each
    # target the spell requires" once -- in the rule that answers the
    # question -- and ORed together the common one won the reserved slot
    # and the precise one was lost.
    best: list[Passage] = []
    for phrase in phrases:
        for passage in matching(f'"{phrase}"', 1):
            if passage not in best:
                best.append(passage)
        if len(best) >= room:
            break
    return tuple(best[:room])
