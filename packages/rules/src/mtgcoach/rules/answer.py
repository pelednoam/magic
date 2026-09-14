"""What an answer to a rules question may be, and how we know it is not invented.

The turn coach is checked by comparing its choice against options the engine
enumerated. A rules question has no options to compare against, so it is checked
a different way: **the answer may only cite passages that were put in front of
it.** Retrieval happens first, the passages go in the prompt verbatim, and an
answer citing anything else is refused unread.

That is weaker than the turn coach's check, and the difference has a name.
``coach.advice.trusted`` means *the engine agrees with this choice*. Nothing
here can mean that: a citation is not a proof, and "trample doubles all damage
[702.19b]" cites a real retrieved rule that says nothing of the kind. So what
this returns is ``cited`` -- every rule it named was one we put in front of it,
and it named at least one. The word "trusted" is deliberately not used on this
side of the project, because it would be a lie in a place where a child reads
the result.

What that buys, and what matters at a kitchen table, is that every answer comes
with a number somebody can look up, that the number is real, and that the rule
it points at is printed underneath the answer for them to read.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from mtgcoach.rules.citations import resolved

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.rules.corpus import Passage


@dataclass(frozen=True, slots=True)
class Answer:
    """One answer to one rules question."""

    #: The answer for whoever is teaching, in full.
    answer: str = ""
    #: The same thing for the person being taught. §3's whole point.
    in_short: str = ""
    #: The rules it is drawn from, by reference. Never empty in an answer that
    #: passes: one with nothing to look up is one nobody can check.
    citations: tuple[str, ...] = field(default_factory=tuple[str, ...])
    #: Where the answer stops. A question the given rules do not settle is
    #: answered by saying so, which is a better answer than a guess.
    unsure: str = ""


#: How much model text a refusal may quote back.
_READABLE = 80


class Asker(Protocol):
    """Something that answers a rules question. A model, usually."""

    def ask(self, question: str, briefing: str) -> Answer:
        """Answer it.

        Raises:
            ExplainerError: If no answer could be obtained.
        """
        ...


def settle(answer: Answer, supplied: Sequence[Passage]) -> tuple[Answer, tuple[str, ...]]:
    """The answer with its citations resolved, and every problem left with it.

    Resolving first is what stops the check punishing decoration. A model shown
    ``[702.19b] (Trample) ...`` will sometimes cite "702.19b (Trample)", or
    "rule 702.19b", or "702.19b." -- all of which name a rule it was given, and
    none of which is that rule's reference as spelled. Every live answer in the
    first smoke test was thrown away for exactly this.

    So a citation is matched by what it *names* and then rewritten to the
    supplied spelling, which is also what the client needs to line an answer up
    against the rules beside it. What is not relaxed is the part that matters:
    after resolving, a citation is either one of the supplied references or it
    is reported.
    """
    settled = Answer(
        answer.answer,
        answer.in_short,
        resolved(answer.citations, supplied),
        answer.unsure,
    )
    return settled, verify(settled, supplied)


def verify(answer: Answer, supplied: Sequence[Passage]) -> tuple[str, ...]:
    """Every way this answer goes beyond what it was given, empty when none."""
    return (*_check_citations(answer, supplied), *_check_substance(answer))


def _check_citations(answer: Answer, supplied: Sequence[Passage]) -> tuple[str, ...]:
    """Every rule it cites has to be one that was in the prompt."""
    given = {passage.reference for passage in supplied}
    invented = [cited for cited in answer.citations if cited not in given]
    if invented:
        return (f"cites rules it was not given: {_short(', '.join(sorted(invented)))}",)
    return ()


def _short(value: str) -> str:
    """Model text, cut to a length a person can read.

    This ends up in the refusal on screen and every character of it came out of
    a model; there is no length a malformed citation cannot be.
    """
    return value if len(value) <= _READABLE else value[:_READABLE] + "..."


def _check_substance(answer: Answer) -> tuple[str, ...]:
    """An answer has to say something, and say where it got it.

    An uncited answer is the shape a remembered one takes: fluent, plausible,
    and impossible to look up. There is no exception for one that also fills in
    ``unsure`` -- there was, and it was a hole straight through the check: a
    confident uncited paragraph plus ``unsure="one minor detail"`` passed. The
    admission has to be the whole answer, not a disclaimer attached to one.
    """
    if not answer.answer and not answer.in_short:
        return ("says nothing",)
    if not answer.citations:
        return ("makes a claim with no rule to look up",)
    return ()


def cited(answer: Answer, supplied: Sequence[Passage]) -> bool:
    """Whether every rule this answer names was one it was given.

    Not "whether it is right". See the module docstring: nothing here reads the
    rule and checks the claim against it.
    """
    return not verify(answer, supplied)


def refusal(problems: Sequence[str]) -> Answer:
    """What to show instead of an answer that failed its checks.

    Not silence. The retrieved rules go to the client either way, so a refused
    answer still leaves the player with the actual rules on screen -- which is
    the part that was certainly true all along.
    """
    return Answer(
        # Without "if there are any". The commonest refusal is an answer that
        # cited nothing, and the commonest reason for *that* is that nothing
        # was retrieved -- so the old wording pointed at rules below in exactly
        # the case where there were none.
        answer=(
            "The answer did not stay inside the rules it was given, so it is not shown. "
            "Any rules listed below are the real ones; read those."
        ),
        in_short="I could not answer that one safely. Let us read the card together.",
        unsure="; ".join(problems),
    )
