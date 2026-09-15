"""What a game was played under: which engine, which card data, which rules.

``docs/DECISIONS.md`` item 5, decided: *"a game is pinned to the versions it
was played under. A journal records its events and not the engine, card data or
rules revision that produced them -- which is exactly what made item 6 a
question, and what made a whole directory of journals unreadable when priority
arrived with nothing recording that they predated it."*

Three revisions, because there are three things that can change under a
recorded game and each changes it differently:

- the **engine** decides which events are legal, so a stricter one makes an
  old journal unreplayable. That is the failure that happened.
- the **card data** decides what a card does, so a re-sealed fixture can change
  what the same events *meant* while every one of them still applies.
- the **rules** are what an answer was judged against, so a question answered
  under one revision may be answered differently under the next.

One value rather than three fields, because they are always wanted together:
they ride the wire as one object, go into a journal as one line, and are
compared as one thing when a recording is read back.

**Nothing gates on them.** They are diagnostic. The engine itself is the gate:
it refuses an event it no longer considers legal, and ``replays`` then skips
that game rather than show a board the events did not produce. What these do is
turn "this journal will not open" into "this journal was made by a different
engine", which is the difference between a puzzle and a fact.
"""

from __future__ import annotations

from dataclasses import dataclass

#: What an unknown revision is recorded as. Empty rather than "unknown", so
#: that a reader can tell it from a revision somebody called that -- and so a
#: journal written before this existed reads back as three empty strings rather
#: than three claims.
UNRECORDED = ""


@dataclass(frozen=True, slots=True)
class Sources:
    """The three revisions a game was played under.

    Every field defaults to ``UNRECORDED``, which is what a journal from before
    any of this existed reads back as. That is deliberate and it is the whole
    of the migration: an old recording is missing the information, not wrong
    about it, and saying so is better than refusing to open it.
    """

    #: A digest over the rules engine's source; see ``core.revision``.
    engine: str = UNRECORDED
    #: The sha256 of the sealed card-data fixture, as its manifest records it.
    cards: str = UNRECORDED
    #: The date the Comprehensive Rules say they took effect; see
    #: ``rules.effective``. Empty on a server with no rules installed, which is
    #: a supported way to run this -- the tracker and the engine do not need
    #: them, and only the question box goes away.
    rules: str = UNRECORDED

    def differs_from(self, other: Sources) -> tuple[str, ...]:
        """Which revisions are not the same, named, for a person to read.

        A field nobody recorded is not a difference. Comparing an old journal
        against today would otherwise report all three as changed, which says
        nothing except that the journal is old -- and would drown the case
        worth seeing, where a game records two of the three and one has moved.
        """
        return tuple(
            name
            for name, mine, theirs in (
                ("engine", self.engine, other.engine),
                ("card data", self.cards, other.cards),
                ("rules", self.rules, other.rules),
            )
            if mine != theirs and UNRECORDED not in (mine, theirs)
        )
