"""The rules this engine does not carry out, said where a player reads them.

``carrying`` is the same idea about *cards*: what the engine will not do if you
play this one, in words, so that a beginner reads "the tracker will not apply
its +3/+3" instead of a confident board that is wrong by three points. Nothing
said the same about the *rules*, and the priority model is the first place that
gap becomes visible: a stack that holds only spells looks complete, and a child
who learned from it that a trigger cannot be answered would have learned
something that is not a rule of Magic.

So this is a sibling of that module rather than part of ``priority``. What
priority does is one question; what the model of it leaves out is another, and
the second one is answered for a reader rather than for the engine.

Position-dependent, not a constant banner, so what a player reads is about the
moment in front of them. It rides the wire in ``TurnReport.not_modelled`` and
the app prints it beside the stack.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState

#: What this engine's priority model does not do, in the words a player needs.
#:
#: The project's standing rule is that an unmodelled feature is a gap and a
#: wrong board is a lie, and that a gap has to be disclosed somewhere a player
#: sees it. A priority system that handled only spells while *looking* complete
#: would be the second thing: a child would learn that a trigger cannot be
#: answered, which is not a rule of Magic.
ONLY_SPELLS = (
    "only spells go on the stack here -- an activated or triggered ability does not, "
    "so nobody receives priority to answer one (CR 117.1b, CR 603.3)"
)

#: CR 514.3a. ``steps`` already calls the plain version the safe side of the
#: approximation; this is the side a player is told about.
CLEANUP_STOP = (
    "a trigger or a discard in the cleanup step would hand out priority; "
    "this engine ends the step instead (CR 514.3a)"
)


def disclosures(state: GameState) -> tuple[str, ...]:
    """What the priority model does not cover, here, in the engine's own words.

    Position-dependent rather than a constant banner, so that what a player
    reads is about the moment in front of them. Empty once the game is over:
    nothing more can happen in one, so there is nothing left to disclose.
    """
    if state.over is not None:
        return ()
    if state.step is Step.CLEANUP:
        return (ONLY_SPELLS, CLEANUP_STOP)
    return (ONLY_SPELLS,)
