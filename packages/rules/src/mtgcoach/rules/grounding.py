"""Checking an answer's load-bearing words against the evidence it was given.

``answer.verify`` establishes that every rule an answer cites was one we put in
front of it. That is a check on where the *references* came from and nothing
else, and the review's probe shows exactly how far it does not reach:

    Answer: Trample doubles all damage.
    Citation: 702.19b

passes. 702.19b was retrieved, it is about trample, and it says nothing about
doubling anything. A parent reads a fluent sentence with a real rule number
under it, and a nine-year-old believes it.

Reading an answer and deciding whether it follows from a rule needs another
model, and a checker that pretended to do it deterministically would be worse
than the honest ``cited`` flag -- it would put the word "checked" on the same
sentence. So this does something narrower and exact: it takes the two kinds of
word a rules claim cannot be paraphrased around, and requires each to appear
*somewhere in the evidence the prompt contained*.

- **Arithmetic.** Doubling, halving and tripling are operations the rules name
  in so many words -- 701.10e writes "double the number", 701.10f "double the
  amount", and the document uses "twice", "halve" and "triple" where it means
  them. An answer that doubles something no supplied rule and no supplied card
  doubles did that arithmetic from memory. This is what catches the probe.
- **Subject.** A keyword ability the answer *attributes to something* -- "has
  flying", "with trample", "deathtouch means" -- has to be mentioned by
  something in the prompt. Retrieval indexes the whole document, so a question
  about deathtouch retrieves the deathtouch rules, and the board's cards now
  carry their own keywords in their quoted text; an answer attributing an
  ability nothing in the prompt mentions is not drawing on the evidence at all.
  Only possible now the card text is in the prompt: before it, "your Angel has
  flying" had nothing to be grounded against and would have been refused.

**What was rejected.** Requiring the words in the *cited* passages rather than
in everything supplied is the stronger check, and it refuses a correct answer
that leans on a supplied passage it forgot to cite -- a refusal a parent cannot
act on and cannot fix. Following ``keywords``: one narrow signal, and be wrong
in the direction that refuses less.

``unsure`` is not scanned. That field is where an answer says what it cannot
settle, and "these rules do not say whether the damage is doubled" is the
sentence this project most wants written; scanning it would refuse the
admission and teach the model to leave it out.

**This is a floor, not a ceiling.** Every problem it reports is real; the
absence of one establishes nothing beyond itself, since an answer can be wrong
in prose that contains no arithmetic and names no ability. That is why no flag
downstream is named ``correct`` and why the rules are printed under the answer.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Final

from mtgcoach.rules.keywords import NONE, Keywords

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.rules.corpus import Passage


@dataclass(frozen=True, slots=True)
class Given:
    """What went into the prompt besides the retrieved rules.

    One value rather than two arguments threaded side by side, for the reason
    ``keywords.Keywords`` is one: they are always used together, and a caller
    that passed one and not the other would weaken the check with nothing
    saying so. ``asking.answered`` builds it, from exactly what the prompt got.
    """

    #: The card text quoted into the prompt. Evidence in the same sense a rule
    #: is: it went in verbatim, so a claim can be grounded in it.
    cards: tuple[str, ...] = ()
    #: The keyword abilities this document defines, off ``RuleIndex``. Empty
    #: means no ability claim is checked at all, which is why the route has a
    #: test of its own asserting that it passes them through.
    keywords: Keywords = NONE


#: What a caller with no evidence to add gets: the arithmetic check still runs
#: against the supplied passages, and the keyword check has nothing to run on.
NOTHING: Final = Given()

#: Words that name the same arithmetic, grouped, with what to call it in a
#: refusal. Grouped because "doubles" and "twice" are one operation in English
#: and the rules use both, so requiring the answer's exact spelling would
#: refuse a correct paraphrase of a rule that was right there.
_ARITHMETIC: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("doubled", re.compile(r"doubl\w*|twice")),
    ("halved", re.compile(r"halv\w*|\bhalf\b")),
    ("tripled", re.compile(r"tripl\w*|thrice")),
)

#: A multiplier word in front of "strike" is a keyword ability's name, not an
#: operation. Double strike doubles nothing: it adds a second combat damage
#: step (CR 702.4b). Left in, the phrase grounded a doubling claim against any
#: passage that merely mentioned the ability -- 702.4b mentions it four times --
#: so it comes out of the answer and the evidence alike.
_ABILITY_NAME: Final = re.compile(r"\b(?:doubl\w*|tripl\w*)\s+strike\b")

#: A word, for finding keyword names in prose.
_WORD: Final = re.compile(r"[a-z]+")

#: What makes a word the name of a Magic ability rather than ordinary English.
#: A hundred and sixty keywords are single real words -- reach, fear, shadow,
#: support, recover -- so a bare match is evidence of nothing: "the rules
#: support this" is English, and refusing it would make the check a nuisance
#: that gets switched off, taking the arithmetic check with it. An ability is
#: *attributed*: something has it, is granted it, or the answer says what it
#: means.
_ATTRIBUTED_BEFORE: Final = frozenset(
    ["has", "have", "had", "with", "gains", "gain", "gained", "grants", "grant", "keyword"]
)
_ATTRIBUTED_AFTER: Final = frozenset(["means", "ability", "keyword"])


def problems(said: str, supplied: Sequence[Passage], given: Given = NOTHING) -> tuple[str, ...]:
    """Every load-bearing word in ``said`` that the evidence does not carry.

    ``said`` is the answer's prose -- the adult sentences and the child's
    together, because "your creature hits twice as hard" is the half a
    nine-year-old reads and it has to be checked like any other claim.
    """
    evidence = _evidence(supplied, given)
    return (
        *_ungrounded_arithmetic(said, evidence),
        *_ungrounded_abilities(said, evidence, given.keywords),
    )


def _evidence(supplied: Sequence[Passage], given: Given) -> str:
    """Everything the prompt supplied, as one body of text to look words up in.

    Titles as well as bodies: "Trample" is a heading, and a passage under it
    mentions the ability whether or not its sentence repeats the word.
    """
    parts = [f"{passage.title} {passage.text}" for passage in supplied]
    parts.extend(given.cards)
    return " ".join(parts)


def _ungrounded_arithmetic(said: str, evidence: str) -> tuple[str, ...]:
    """Arithmetic the answer performs that nothing it was given performs."""
    missing = sorted(_arithmetic_in(said) - _arithmetic_in(evidence))
    return tuple(
        f"says something is {name}, which no rule and no card it was given says" for name in missing
    )


def _arithmetic_in(text: str) -> frozenset[str]:
    """Which of the three operations this text performs, by name."""
    bare = _ABILITY_NAME.sub(" ", text.casefold())
    return frozenset(name for name, written in _ARITHMETIC if written.search(bare))


def _ungrounded_abilities(said: str, evidence: str, keywords: Keywords) -> tuple[str, ...]:
    """Abilities the answer attributes that nothing it was given mentions.

    The evidence side is a bare word match, not an attribution: a rule titled
    "Trample" mentions trample, and requiring the document to phrase it as
    "has trample" would ground almost nothing.
    """
    mentioned = frozenset(_WORD.findall(evidence.casefold()))
    missing = sorted(_attributed_in(said, keywords) - mentioned)
    return tuple(
        f"says something has {name}, which no rule and no card it was given mentions"
        for name in missing
    )


def _attributed_in(text: str, keywords: Keywords) -> frozenset[str]:
    """Which keyword abilities this text attributes to something.

    Exact spellings only, unlike ``keywords.ordinary``, which has to match
    inflections because the search index stems them. Here an inflection is
    *evidence against* the keyword reading -- prose writes "has flying" and
    "trample means", while "your life reaches zero" is English -- so ignoring
    them errs towards checking less, which is the direction a refusal may err
    in. ``keywords``'s own "a number word after it" signal is not needed on top
    of the attribution one: nothing writes "has reach zero".
    """
    words = _WORD.findall(text.casefold())
    return frozenset(
        word
        for index, word in enumerate(words)
        if word in keywords.names and _attributed(words, index)
    )


def _attributed(words: list[str], index: int) -> bool:
    """Whether the word at ``index`` is named as an ability something has."""
    before = words[index - 1] if index else ""
    after = words[index + 1] if index + 1 < len(words) else ""
    return before in _ATTRIBUTED_BEFORE or after in _ATTRIBUTED_AFTER
