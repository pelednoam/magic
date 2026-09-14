"""Asking the coach, and refusing to pass on an answer the engine disputes.

The route is three lines because everything that could go wrong is here. §8's
rule -- Claude explains, the engine rules -- is a single gate, and it lives at
exactly one place so there is no second path to the client that skips it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api import views
from mtgcoach.coach.advice import refusal, verify
from mtgcoach.coach.briefing import brief

if TYPE_CHECKING:
    from mtgcoach.api.context import Position
    from mtgcoach.api.views import Json
    from mtgcoach.coach.advice import Explainer


def coached(explainer: Explainer, position: Position) -> dict[str, Json]:
    """One turn's advice, marked with whether it survived checking.

    A failed check is not an error and not silence: the client gets the
    ``refusal`` text and ``trusted: false``, so the player is told the words are
    missing rather than left wondering why the panel went quiet. The engine's
    own advice is in the snapshot either way, and that part was never in doubt.

    Raises:
        ExplainerError: If no answer could be got at all.
    """
    report = position.report
    said = explainer.explain(report, brief(report))
    problems = verify(said, report)
    return {
        "explanation": views.explanation(refusal(problems) if problems else said),
        "trusted": not problems,
        # Which board this is about. A minute is long enough for somebody to
        # play a card while the model is thinking, and the client was left
        # comparing against the version it *had* when it asked -- close enough
        # in practice, and a guess. This makes it a fact.
        "version": position.revision,
    }
