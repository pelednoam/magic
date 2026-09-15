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
other term, and it can lose. It lost, at first, to a different weakness
entirely: "what happens when my hit points reach zero?" retrieved the rules for
**reach**, the keyword ability, because the question contains the word and a
keyword's heading outranks a common phrase. ``keywords`` addresses that one --
this map does not, and the two are separate for that reason.

Every target must actually occur in the Comprehensive Rules.
``tools/check_rules_phrasing.py`` checks that against the installed document,
because a target the rules do not contain adds nothing to a query but noise,
and nothing else would ever notice.
"""

from __future__ import annotations

import re

from mtgcoach.rules.wording import (
    DIES,
    ENTERED,
    LEGAL_TARGET,
    LETHAL,
    LIFE_TOTAL,
    NO_CARDS,
    OUT_OF_LIFE,
    SUMMONING_SICKNESS,
    TARGET_CHOICE,
)

#: Each entry: something a beginner types, and the rules' words for it. Matched
#: case-insensitively against the whole question, and the original words are
#: kept as well -- this adds to a query, it does not replace it.
PHRASES: tuple[tuple[re.Pattern[str], tuple[str, ...]], ...] = (
    # Summoning sickness, six ways. A child says "just played", a parent who
    # last played in 1998 says "came into play", and neither says the one
    # phrase that finds the rule.
    #
    # The leading lookahead is the scope. Without it "I just cast a sorcery"
    # and "the artifact came into play" both asked about summoning sickness,
    # which is a rule about creatures attacking and tapping -- so an irrelevant
    # phrase went into a prompt that holds eight passages and pushed a relevant
    # one out.
    (
        re.compile(
            r"(?=.*\b(?:creature|creatures|guy|guys|attacks?|attacked|attacking|attacker"
            r"|blocks?|blocked|blocking|blocker|taps?|tapped|tapping|untapped)\b)"
            r".*\b(?:"
            r"(?:came?|comes|coming) into play|"
            r"(?:just|only just|newly) (?:played|cast|summoned|arrived|came out)|"
            r"played (?:it |him |her |them )?this turn|"
            r"(?:entered|enters|came onto) the battlefield this turn|"
            r"(?:brand[- ])?new creature"
            r")\b",
            re.IGNORECASE | re.DOTALL,
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
    # Running out of life, in the words a person uses for it. The rules say
    # "0 or less life" and a question says "reaches zero", "runs out", "hits
    # nothing left" -- and the digit is why none of them matched.
    # A creature dying, which is the commonest question in the box and returned
    # eight passages about *dice*. The rules define "dies" (700.4) and explain
    # why (704.5g/h), and the bare word cannot reach either: with porter
    # stemming "die" and "dies" are one term, and the document's own uses of it
    # are the planar die and rule 706, "Rolling a Die" -- a heading, which
    # outranks everything. So the phrases are added and the word is dropped;
    # see ``INSTEAD``.
    (
        re.compile(
            r"(?=.*\b(?:creature|creatures|guy|guys|bear|it|damage|combat|fight"
            r"|attacks?|attacking|blocks?|blocking|toughness)\b)"
            r".*\b(?:dies?|died|dying|dead|death|killed?|destroyed?)\b",
            re.IGNORECASE | re.DOTALL,
        ),
        (DIES, LETHAL),
    ),
    # A deck running out, in the words a person uses. "I run out of cards" and
    # "my deck is empty" share no phrase with 121.4, which is the rule.
    (
        re.compile(
            r"\b(?:"
            r"run(?:s|ning)?\s+out\s+of\s+cards|"
            r"(?:deck|library)\s+(?:is\s+)?(?:empty|runs?\s+out|has\s+no\s+cards)|"
            r"no\s+cards?\s+(?:left|in\s+my\s+(?:deck|library))|"
            r"out\s+of\s+cards"
            r")\b",
            re.IGNORECASE,
        ),
        (NO_CARDS,),
    ),
    # A spell that needs something to point at and has nothing. The question
    # says "without a creature"; the rules say "legal target".
    (
        re.compile(
            r"\b(?:"
            r"without\s+(?:a\s+|any\s+)?(?:creature|creatures|target|targets)|"
            r"(?:no|nothing|none)\s+(?:\w+\s+){0,2}?to\s+target|"
            r"no\s+(?:legal\s+)?targets?|"
            r"nothing\s+to\s+(?:point|aim|cast)\s+(?:it\s+)?at"
            r")\b",
            re.IGNORECASE,
        ),
        (TARGET_CHOICE, LEGAL_TARGET),
    ),
    (
        re.compile(
            r"\b(?:"
            r"(?:life|life total|hit points|hp)\s+"
            r"(?:reach(?:es)?|hits?|gets?\s+to|drops?\s+to|goes?\s+to|is|are)\s*"
            r"(?:zero|0|nothing|none)|"
            r"reach(?:es|ed)?\s+(?:zero|0)\s+life|"
            r"run(?:s|ning)?\s+out\s+of\s+life|"
            r"no\s+life\s+left|"
            r"lose\s+all\s+(?:my\s+|your\s+|their\s+)?life"
            r")\b",
            re.IGNORECASE,
        ),
        (OUT_OF_LIFE,),
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
