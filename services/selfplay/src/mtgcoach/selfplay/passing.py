"""What it takes to end a step, in events.

One function, and its own module because it is the only place in the harness
that encodes a *sequence* of the rules rather than a loop over decisions. The
game loop next door reads as a loop; this reads as CR 500.2, and the day an
agent learns to answer a spell instead of passing, this is the line that
changes and nothing else in ``playing`` has to move.

It also keeps the harness honest about a thing worth being honest about. The
loop used to end a step by sending ``AdvanceStep`` and nothing else, and the
engine used to accept it -- which was exactly the half of CR 500.2 the rule
itself warns against: a step does not end because the stack happens to be
empty, it ends because each player has had the chance to add something to it
and declined. The declining is now an event, applied through the reducer and
written into the log, so a self-play game's log is a log a person could have
produced at the table.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core import priority
from mtgcoach.core.events import AdvanceStep, PassPriority

if TYPE_CHECKING:
    from mtgcoach.core.events import Event
    from mtgcoach.core.state import GameState


def ending(state: GameState) -> tuple[Event, ...]:
    """Everything it takes to end this step: the passes, then the step itself.

    CR 500.2 for a step in which players receive priority: every player still
    holding a chance to act passes, in the order they act, and then the step
    ends. CR 500.3 for the untap and cleanup steps, which hand out no priority
    -- there is nobody to pass, so ``yet_to_pass`` is empty and the step simply
    ends.

    The passes are the harness's own policy, not a rule it discovered. No agent
    has a response to give: a ``Move`` names a card to play or an attack to
    make, and there is no "answer that spell" to name. So passing is the only
    thing either seat could truthfully be said to do here, and it is sent as
    what it is rather than assumed away. ``applying.cast_and_resolve`` makes
    the same admission about the same limitation.
    """
    return (*(PassPriority(player=seat) for seat in priority.yet_to_pass(state)), AdvanceStep())
