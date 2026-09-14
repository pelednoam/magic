"""The checks about what an explanation does *not* say.

A model that forgets to mention an unmodelled card, or a trigger that is firing
right now, is indistinguishable from one that decided it did not matter -- and
a beginner reads silence as "counted". So these are all the same shape: work
out what was owed, look for it in the words, and report what is missing by
name.

Matching is the interesting part. A plain substring search found "Rat" inside
"strategy", so an explanation that never mentioned the Rat was credited with
mentioning it -- and in a check about silence a false positive is the whole
failure. ``mentions`` is the word-boundary version, shared with ``checks``.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.report import TurnReport


def honesty(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """Where the engine stops, the explanation has to say so -- about each card.

    §8: "If the engine hits an ``Unmodeled`` effect, say so and show the card
    text." Asked for in the prompt and enforced here, because a model that
    forgets is indistinguishable from one that decided the card did not matter.

    Checked *per card*, not as a count. Requiring only that ``check_yourself``
    be non-empty meant one arbitrary sentence discharged every obligation on
    the board: a model that mentioned the Pacifism and said nothing about the
    Equipment passed, and the player read the silence as "counted".
    """
    owed = (*report.unknown, *report.attacks.caveats)
    said = " ".join(explanation.check_yourself)
    missing = [item for item in owed if not mentions(said, _named(item))]
    if not missing:
        return ()
    return (f"says nothing about {len(missing)} of {len(owed)} not modelled: {missing[:3]}",)


def triggers(explanation: Explanation, report: TurnReport) -> tuple[str, ...]:
    """A trigger that is firing has to be named somewhere in the answer.

    Stopping the *shortcut* passing over a trigger was only half of it: the
    model was then asked, and nothing made it mention the trigger either. An
    explanation that says "nothing to do, pass the turn" over a firing trigger
    is the same wrong answer, arrived at the long way round, and it was marked
    trusted. Anywhere in the words counts -- this is a check on silence, not on
    where a model chose to put it.
    """
    if not report.reminders:
        return ()
    said = everything(explanation)
    silent = [r.name for r in report.reminders if not mentions(said, r.name)]
    if not silent:
        return ()
    return (f"says nothing about {len(silent)} trigger(s) firing now: {silent[:3]}",)


def mentions(said: str, name: str) -> bool:
    """Whether ``said`` names this card, as a word rather than as letters.

    A plain substring search found "Rat" inside "strategy", so an explanation
    that never mentioned the Rat was credited with mentioning it -- and these
    are the checks where a false positive is the whole failure.
    """
    return re.search(rf"(?<!\w){re.escape(name)}(?!\w)", said, re.IGNORECASE) is not None


def everything(explanation: Explanation) -> str:
    """Every word the explanation carries, for checks about silence."""
    return " ".join(
        (
            explanation.because,
            explanation.in_short,
            *explanation.watch_out,
            *explanation.check_yourself,
        )
    )


def _named(item: str) -> str:
    """The card an unmodelled-thing sentence is about.

    Both producers write "<name>: <reason>" -- ``report._unknown`` and
    ``statics.caveats``. The name is what a model would repeat; the reason is
    the engine's own words and asking for those back would be asking it to
    quote us.
    """
    return item.split(":", 1)[0].strip()
