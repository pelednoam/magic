"""Answering a rules question: retrieve, ask, check, hand over.

The one path a rules answer can reach a client through, so the citation check
cannot be gone round. The order is the whole design:

1. **Search first.** The question goes to the Comprehensive Rules index before
   it goes to a model, so the passages are chosen by the question rather than
   by what a model felt like quoting.
2. **Quote verbatim.** Those passages go into the prompt as text.
3. **Check afterwards.** Every reference the answer cites must be one of the
   ones supplied, compared exactly. That is a check on the *citations*, not on
   the prose, which is why what goes on the wire is called ``cited``.
4. **Check the claims against the evidence, as far as that can be done.** The
   arithmetic and the keyword abilities in the answer must be words the prompt
   actually carried -- see ``rules.grounding``, which is a floor under an
   answer and not a verdict on one. That goes on the wire as ``grounded``, a
   second boolean rather than a stronger reading of the first, and the two are
   reported separately because they fail for different reasons.

Neither boolean is ``correct``, and ``unchecked`` says which question no check
here answers, in the server's words, so the app can print it without deciding.

A question that matches nothing is not asked at all. It used to be, with a
prompt saying "there is nothing to cite, say so" -- and then the checker
refused the answer for having no citations, because it could not have any. The
player got a refusal where the truthful answer was "nothing in the rules
matched that", which the server can say itself, instantly and for nothing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.rules.answer import Answer, cited, grounded, settle
from mtgcoach.rules.grounding import Given
from mtgcoach.rules.question import brief
from mtgcoach.rules.refusing import UNCHECKED, refusal

if TYPE_CHECKING:
    from mtgcoach.api.context import Position
    from mtgcoach.api.views import Json
    from mtgcoach.rules.answer import Asker
    from mtgcoach.rules.search import RuleIndex


def answered(
    asker: Asker,
    index: RuleIndex,
    question: str,
    position: Position,
) -> dict[str, Json]:
    """One question's answer, marked with whether it stayed inside the rules given.

    Raises:
        ExplainerError: If no answer could be got at all.
    """
    passages = index.search(question)
    if not passages:
        return _nothing_matched(position.revision)
    briefing = brief(question, passages, position.report, position.board)
    # Built from the same board the prompt was built from, so the check asks
    # about the evidence the model actually had. Passing the index's keywords
    # is what switches the ability half of the grounding check on at all.
    given = Given(cards=_quoted(position), keywords=index.keywords)
    said, problems = settle(asker.ask(question, briefing), passages, given)
    return {
        "answer": _answer(refusal(problems) if problems else said),
        # `cited`, not `trusted`. It means every rule the answer named was one
        # we retrieved for it, and that it named at least one -- not that the
        # answer is right about what those rules say. The turn coach's
        # `trusted` is a stronger claim and keeps its stronger word.
        "cited": cited(said, passages),
        # The other axis: the arithmetic and the abilities in the answer were
        # words the prompt carried. Separate from `cited` because they fail
        # separately -- an answer can cite perfectly and double something no
        # rule doubles, which is the finding this pair was added for -- and
        # neither of them is `correct`; see `unchecked`.
        "grounded": grounded(said, passages, given),
        # What no check here establishes, in sentences. The app prints them; it
        # decides nothing about the rules, and a boolean named for what is not
        # known would read as a warning light that is off.
        "unchecked": list(UNCHECKED),
        #: Whether the search found anything at all. Always true here; see
        #: `_nothing_matched` for the case where it is not.
        "matched": True,
        # Which board this was asked over; see `coaching.coached`. A rules
        # question carries the battlefield in its prompt, so its answer goes
        # stale the same way turn advice does.
        "version": position.revision,
        # The passages it was given, whether or not it cited them. The player
        # can then read the rule themselves, which is the point of retrieving
        # it -- and is the part of the answer that is certainly true.
        "rules": [{"reference": p.reference, "title": p.title, "text": p.text} for p in passages],
    }


def _nothing_matched(revision: int) -> dict[str, Json]:
    """What to say when the search found nothing.

    Not a refusal, and not a model call. There is nothing to cite, so anything
    a model said would be refused for having no citations -- and "I searched
    and found nothing" is both true and the most useful thing available.
    """
    return {
        "answer": _answer(
            Answer(
                answer=(
                    "Nothing in the Comprehensive Rules matched that question. Try naming "
                    "a card, a keyword, or a step of the turn."
                ),
                in_short="I could not find a rule about that. Let us read the card together.",
            )
        ),
        # Not cited, because nothing was retrieved to cite -- but `matched`
        # tells the client which of the two this is. Without it the app showed
        # "the answer did not stay inside the rules" over an answer that never
        # left them, which is both wrong and alarming.
        "cited": False,
        # Vacuously true: there were no claims to ground and nothing to ground
        # them in. Said as true rather than false because false here would put
        # "this answer went beyond its evidence" over the sentence "I could not
        # find a rule about that", which is the one answer on this route that is
        # certainly within it.
        "grounded": True,
        "unchecked": list(UNCHECKED),
        "matched": False,
        "version": revision,
        "rules": [],
    }


def _quoted(position: Position) -> tuple[str, ...]:
    """The card text the prompt carried, for the grounding check to ground in.

    Empty when the route was asked without a board, which is not a case the
    server produces -- ``position(board=True)`` is how this route builds one --
    but is a case a test can, and an empty tuple checks less rather than
    claiming more.
    """
    if position.board is None:
        return ()
    return tuple(card.text for card in position.board.cards)


def _answer(said: Answer) -> dict[str, Json]:
    """One answer, on the wire."""
    return {
        "answer": said.answer,
        "in_short": said.in_short,
        "citations": list(said.citations),
        "unsure": said.unsure,
    }
