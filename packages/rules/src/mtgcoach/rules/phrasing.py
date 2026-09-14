"""What a beginner calls a rule, and what the rules call it.

Retrieval is a full-text search, so a question only finds a rule if the two
share words. Most of the time they do, and where they do not the document
usually bridges the gap itself: rule 403.5 says the battlefield used to be
called "in play", and 404.1 says a graveyard is a discard pile. Ask about
either in the old words and the rule explaining the old words comes back.

There is one gap the document cannot bridge, because it is not a word, it is a
paraphrase. Found live: *"can a creature that came into play this turn
block?"* -- which is the question a nine-year-old asks in their first game, and
possibly the single most common beginner question about combat. The answer is
rule 302.6, and 302.6 does not contain "came into play", or "this turn", or
anything else the question says. It says a creature cannot attack "unless it
has been under its controller's control continuously since their most recent
turn began", and then -- helpfully, and this is the whole hinge -- adds that
this is informally called the "summoning sickness" rule. So retrieval returned
eight passages about blocking, none of them 302.6, and the answer came back
*"the rules I was given don't talk about how new a creature is"*: honest,
correctly refusing to invent, and useless.

So this maps a paraphrase to the phrase the rules use. Deliberately tiny, and
it must stay tiny: every entry is a decision about what a question is about,
made in advance and without the question in front of it, which is exactly the
kind of cleverness that makes retrieval worse. An entry earns its place by
being a *concept* a beginner has no rules-vocabulary for -- not a synonym, and
not a word the document already explains.

What this is *not* is a guarantee. An added phrase competes on bm25 like every
other term, and it can lose. Verified live: "what happens when my hit points
reach zero?" still retrieves the rules for **reach**, the keyword ability,
because the question happens to contain the word and a keyword's own heading
outranks a common phrase. That is a different weakness -- a word that is
ordinary English and also a Magic keyword -- and this map does not address it.
On the same question without the collision ("how many hit points do we start
with?") the phrase wins and rule 103.4 comes back where nothing useful did
before.

Every target must actually occur in the Comprehensive Rules.
``tools/check_rules_phrasing.py`` checks that against the installed document,
because a target the rules do not contain adds nothing to a query but noise,
and nothing else would ever notice.
"""

from __future__ import annotations

import re

#: The rules' own name for "this creature only just turned up", which is the
#: thing rule 302.6 is about and the thing 302.6 never says. The rules use the
#: phrase twice -- in 302.6 itself and in the glossary entry that points back
#: to it -- so it survives one of them being reworded.
SUMMONING_SICKNESS = "summoning sickness"

#: What the rules call the number a child calls hit points.
LIFE_TOTAL = "life total"

#: The current wording for what a card printed before 2009 called coming into
#: play. Rule 403.5 covers the bare phrase; this finds the rules about the
#: event, which is usually what is being asked about.
ENTERED = "entered the battlefield"

#: Each entry: something a beginner types, and the rules' words for it. Matched
#: case-insensitively against the whole question, and the original words are
#: kept as well -- this adds to a query, it does not replace it.
PHRASES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    # Summoning sickness, six ways. A child says "just played", a parent who
    # last played in 1998 says "came into play", and neither says the one
    # phrase that finds the rule.
    (
        re.compile(
            r"\b(?:"
            r"(?:came?|comes|coming) into play|"
            r"(?:just|only just|newly) (?:played|cast|summoned|arrived|came out)|"
            r"played (?:it |him |her |them )?this turn|"
            r"(?:entered|enters|came onto) the battlefield this turn|"
            r"(?:brand[- ])?new creature"
            r")\b",
            re.IGNORECASE,
        ),
        (SUMMONING_SICKNESS,),
    ),
    # And the old wording on its own. That question is about the event rather
    # than the restriction, so it wants the rules about entering.
    (
        re.compile(r"\b(?:came?|comes|coming) into play\b", re.IGNORECASE),
        (ENTERED,),
    ),
    # A nine-year-old who has played any other game says hit points. The rules
    # never do.
    (
        re.compile(r"\bhit points\b", re.IGNORECASE),
        (LIFE_TOTAL,),
    ),
)

#: Every phrase this module can add, for the checker that keeps them real.
TARGETS = frozenset(target for _pattern, targets in PHRASES for target in targets)


def also(question: str) -> tuple[str, ...]:
    """The rules' own words for anything this question says in other words.

    In the order ``PHRASES`` lists them and without repeats, so that a question
    matching two entries for the same concept adds the phrase once.
    """
    found = [
        target for pattern, targets in PHRASES if pattern.search(question) for target in targets
    ]
    return tuple(dict.fromkeys(found))
