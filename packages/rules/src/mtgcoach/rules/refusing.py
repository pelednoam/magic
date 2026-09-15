"""What a player sees when an answer fails its checks, and what is never checked.

Split from ``answer``, which had reached the line limit and was holding two
different jobs. That module decides whether an answer may be shown; this one
words the outcome. The seam is worth keeping on its own terms: every sentence
here goes on a screen a nine-year-old reads, and none of it is a check -- so it
can be reworded without touching anything that decides.

Both pieces exist for the same reason. A refusal is not silence, and a passed
check is not a guarantee, and in each case the honest thing is a sentence the
server writes and the app prints without interpreting.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from mtgcoach.rules.answer import Answer

if TYPE_CHECKING:
    from collections.abc import Sequence

#: What no check here establishes, in the server's own words, so that the app
#: can print it under every answer without deciding anything. Sentences rather
#: than a flag: a boolean named for what is *not* known reads as a warning
#: light that is off, and a parent deciding whether to repeat a sentence to
#: their child needs it said.
UNCHECKED: Final = (
    (
        "Nothing here has read the cited rules and decided that the answer follows from "
        "them -- that would need a second model, and two models agreeing is not a proof "
        "either. The rules are printed below: they are the part that is certainly true, "
        "and reading them is how this answer gets checked."
    ),
)


def refusal(problems: Sequence[str]) -> Answer:
    """What to show instead of an answer that failed its checks.

    Not silence. The retrieved rules go to the client either way, so a refused
    answer still leaves the player with the actual rules on screen -- which is
    the part that was certainly true all along.

    "Rules and cards", because a refusal is now one of two things and the
    sentence has to cover both: a citation nobody supplied, or a claim no
    supplied rule *or card* makes. ``unsure`` carries which.
    """
    return Answer(
        # Without "if there are any". The commonest refusal is an answer that
        # cited nothing, and the commonest reason for *that* is that nothing
        # was retrieved -- so the old wording pointed at rules below in exactly
        # the case where there were none.
        answer=(
            "The answer did not stay inside the rules and cards it was given, so it is "
            "not shown. Any rules listed below are the real ones; read those."
        ),
        in_short="I could not answer that one safely. Let us read the card together.",
        unsure="; ".join(problems),
    )
