"""Finding the rules a question is about.

Full-text search over the Comprehensive Rules, so that a question is answered
with the rule in front of it rather than from memory. SQLite's FTS5, because it
is already a dependency, it needs no model and no network, and a few thousand
short passages is a size where BM25 over words is simply the right tool.

The search is a *retrieval*, not an answer. It is allowed to be approximate:
what it returns goes into a prompt, and the model reads all of it. What is not
allowed to be approximate is the citation check afterwards, which is exact.
"""

from __future__ import annotations

import sqlite3
import threading
from typing import TYPE_CHECKING, Self

from mtgcoach.rules.corpus import Kind, Passage
from mtgcoach.rules.keywords import NONE, Keywords, keywords_in
from mtgcoach.rules.pointing import pointed_at
from mtgcoach.rules.terms import query, references_in

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence
    from types import TracebackType

_SCHEMA = """
CREATE VIRTUAL TABLE passages USING fts5(
    reference UNINDEXED,
    title,
    body,
    kind UNINDEXED,
    tokenize = 'porter unicode61'
);
"""

#: How many passages a question is answered with. Enough to cover a rule, the
#: subrules under it and the glossary entry; few enough to stay readable.
DEFAULT_LIMIT = 8


class RuleIndex:
    """A searchable copy of the Comprehensive Rules."""

    def __init__(self, connection: sqlite3.Connection, keywords: Keywords = NONE) -> None:
        """Wrap an open connection. Prefer ``RuleIndex.build``.

        ``keywords`` is every one-word keyword ability this document defines,
        which ``query`` needs in order to tell "reach zero" from the ability.
        Read off the passages by ``build``; empty here means no question ever
        has a word set aside, which is how this behaved before.
        """
        self._connection = connection
        self._keywords = keywords
        # The index is built once and then only read, but it is read from
        # FastAPI's threadpool -- the rules route is a plain `def` because
        # asking Claude blocks for a minute, and a plain `def` runs in a
        # worker thread. A connection made on the main thread then raised
        # `ProgrammingError` on every question. `check_same_thread=False`
        # allows the crossing and hands the serialising to us, which is what
        # this lock is: queries are sub-millisecond, so holding it costs
        # nothing next to the subprocess it is about to wait on.
        self._lock = threading.Lock()

    @property
    def keywords(self) -> Keywords:
        """The ability names this document defines.

        Read off the passages by ``build`` and exposed because the answer
        checks need them too: ``grounding`` cannot tell an ability claim from
        ordinary English without the list, and a list written out anywhere but
        the document would be wrong by the next set.
        """
        return self._keywords

    @classmethod
    def build(cls, passages: Iterable[Passage], path: str = ":memory:") -> Self:
        """Index these passages, in memory by default.

        Usable from any thread once built; see ``__init__``.
        """
        # Listed once: `passages` may be a generator, and it is read twice --
        # for the keyword names and for the rows.
        indexed = list(passages)
        connection = sqlite3.connect(path, check_same_thread=False)
        connection.executescript(_SCHEMA)
        connection.executemany(
            "INSERT INTO passages (reference, title, body, kind) VALUES (?, ?, ?, ?)",
            [(p.reference, p.title, p.text, p.kind.value) for p in indexed],
        )
        connection.commit()
        return cls(connection, keywords_in(indexed))

    def __enter__(self) -> Self:
        """Enter a context manager that closes the index on exit."""
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        """Close the connection however the block ended."""
        del exc_type, exc, traceback
        self.close()

    def close(self) -> None:
        """Close the connection.

        Under the lock, because a question in flight on a worker thread is
        holding it: closing underneath one turns a slow answer into a segfault
        rather than an error.
        """
        with self._lock:
            self._connection.close()

    def search(self, question: str, limit: int = DEFAULT_LIMIT) -> tuple[Passage, ...]:
        """The passages most likely to answer this, best first.

        A rule named in the question comes first, exactly. "What does 702.19b
        say?" tokenises to "702" and "19b" and ranked the right rule nowhere in
        particular; asking for it by number is both cheaper and correct, and it
        is the one case where a question says precisely what it wants.

        Then a slot or two for whatever the *paraphrase* map pointed at, found
        by searching for its phrases alone. A phrase in that map is chosen
        because it is the rules' own wording for the question, so a match on it
        is far better evidence than a match on "cast" or "creature" -- and in
        an OR query of common words it loses anyway, because bm25 normalises by
        length and the rules that answer a beginner's question are long.
        "Can I cast Giant Growth without a creature?" put the phrase for
        CR 601.2c in the query, matched it, and ranked it ninth of eight.

        Empty when the question has no searchable words in it, which is a real
        answer -- "what?" is not a question the rules can be looked up for, and
        returning the eight highest-ranked passages for nothing would be worse
        than returning none.
        """
        named = self.cited(references_in(question))[:limit]
        wanted = query(question, self._keywords)
        if not wanted:
            return named
        pointed = pointed_at(self._matching, question, limit, len(named))
        kept = (*named, *pointed)
        found = [p for p in self._matching(wanted, limit) if p not in kept]
        return (*kept, *found)[:limit]

    def _matching(self, wanted: str, limit: int) -> tuple[Passage, ...]:
        """The passages an FTS5 query matches, best first."""
        with self._lock:
            rows = self._connection.execute(
                # bm25 weights the title above the body: a question about
                # trample should find the trample rules before every rule that
                # mentions it in passing.
                "SELECT reference, title, body, kind FROM passages "
                "WHERE passages MATCH ? ORDER BY bm25(passages, 0.0, 4.0, 1.0) LIMIT ?",
                (wanted, limit),
            ).fetchall()
        return tuple(_passage(row) for row in rows)

    def cited(self, references: Sequence[str]) -> tuple[Passage, ...]:
        """The passages with exactly these references, in the order given.

        Exact, unlike the ranked search: a reference either names a passage in
        this index or it does not. Used by ``search`` for a question that gives
        a rule number, and available to a caller that wants to resolve a set of
        citations back to their text. The *check* that a citation was supplied
        lives in ``rules.answer``, which compares against what it handed out
        rather than against the whole corpus -- citing a real rule nobody
        retrieved is exactly the failure being caught.
        """
        found = [self._exact(reference) for reference in references]
        return tuple(passage for passage in found if passage is not None)

    def _exact(self, reference: str) -> Passage | None:
        """One passage by reference, or None."""
        with self._lock:
            row = self._connection.execute(
                "SELECT reference, title, body, kind FROM passages WHERE reference = ? LIMIT 1",
                (reference,),
            ).fetchone()
        return _passage(row) if row is not None else None


def _passage(row: tuple[str, str, str, str]) -> Passage:
    """One row, as the thing it came from."""
    reference, title, body, kind = row
    return Passage(reference, title, body, Kind(kind))
