"""Who may act right now, and what happens when nobody wants to.

The engine had no answer to that at all. ``GameState`` recorded whose *turn* it
was, which is a different question: a player may cast an instant on their
opponent's turn, and the whole of answering a spell happens while it is
somebody else's. With no holder recorded, "you may cast this" could only mean
"the step allows somebody to", so the app cast a spell and resolved it in the
same breath and there was no moment in between for the other player to do
anything. A tracker meant to teach a nine-year-old to hold a trick has to have
a moment to hold it *in*.

Two fields on ``GameState`` carry it:

- ``priority``, the player who may act (CR 117.1), or None when nobody may --
  during the untap step (CR 502.4) and the cleanup step (CR 514.3), and in the
  moment after everybody has passed, when the top of the stack resolves or the
  step ends (CR 117.4).
- ``passed``, who has passed *since the last action*, in order. CR 117.4 says
  "in succession", so anything anybody does empties it. A count would have
  read the same for two players and stopped being true for three.

Nothing here resolves anything, and that is deliberate rather than a gap.
Resolution has to know whether the spell leaves a permanent behind, which is
its type line, which ``core`` does not hold -- so it stays a separate event and
this module's job is to say when that event is allowed. What the engine cannot
model at all is in ``disclosure``, next door, which rides the wire so that a
player reads it rather than a reviewer.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from mtgcoach.core.errors import IllegalEventError
from mtgcoach.core.steps import has_priority, named

if TYPE_CHECKING:
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState


def turn_order(state: GameState) -> tuple[PlayerId, ...]:
    """Every player, the active one first (CR 101.4).

    The order priority travels in. A two-player game makes "the next player in
    turn order" and "the other one" the same thing; this is written as the
    order anyway, because ``PLAYER_COUNT`` is the only reason they coincide and
    a function that quietly assumed it would be the wrong place to find that
    out.
    """
    active = state.active_player
    return (active, *(player for player in state.players if player != active))


def all_passed(state: GameState) -> bool:
    """Whether every player has passed in succession (CR 117.4)."""
    return len(state.passed) >= len(state.players)


def yet_to_pass(state: GameState) -> tuple[PlayerId, ...]:
    """Who still has to pass before anything happens, in the order they act.

    Empty when nobody holds priority -- either the step hands none out, or
    everybody has already passed. What a client shows as "waiting for them",
    and what the self-play harness sends to end a step.
    """
    holder = state.priority
    if holder is None:
        return ()
    order = turn_order(state)
    start = order.index(holder)
    return tuple(
        player for player in (*order[start:], *order[:start]) if player not in state.passed
    )


def lacking(state: GameState, player_id: PlayerId) -> tuple[str, ...]:
    """Why this player may not act right now, empty when they may (CR 117.1).

    A *reason*, in the shape ``legality`` uses and the coach prints on a card,
    and the same sentence ``demanded`` refuses the event with. One wording, so
    the server cannot refuse an action in words that contradict the advice in
    the very same response -- which is the rule ``api.guard`` exists to keep.
    """
    if state.priority == player_id:
        return ()
    if not has_priority(state.step):
        # CR 502.4 and CR 514.3: nobody receives priority at all here, which is
        # a different sentence from "somebody else has it" and a more useful
        # one -- there is nothing to wait for.
        return (f"nobody gets priority during the {named(state.step)}",)
    if state.priority is None and all_passed(state):
        waiting = "the top of the stack resolves" if state.stack else "the step ends"
        return (f"every player has passed, so nothing happens until {waiting}",)
    if state.priority is None:
        # Nobody holds it and nobody has passed. A played game never reaches
        # this -- ``begins`` hands priority out on entering every step that has
        # any -- so it means a board that was assembled rather than played, and
        # ``selfplay.watching`` reports it as broken. Said plainly rather than
        # described as a pass that did not happen: this module may not
        # misstate the rules even about its own state.
        return ("nobody has priority right now",)
    return ("you do not have priority right now",)


def demanded(state: GameState, player_id: PlayerId) -> None:
    """Refuse an action by a player who does not hold priority (CR 117.1a).

    In the reducer rather than only in ``legality``, because ``legality`` needs
    card data to be asked at all and this needs none: a cast by a player who
    may not act is illegal whatever the card is, and a check a caller can skip
    by not asking is not a check.

    Raises:
        IllegalEventError: If ``player_id`` does not hold priority.
    """
    reasons = lacking(state, player_id)
    if reasons:
        msg = f"{player_id!r} cannot act: {reasons[0]}"
        raise IllegalEventError(msg)


def begins(state: GameState) -> GameState:
    """Hand out priority as a step begins: the active player, or nobody.

    CR 117.3a, and it runs *after* the step's turn-based actions, because those
    are dealt with before a player would receive priority (CR 117.2c). Nobody
    receives it during the untap step (CR 502.4) or the cleanup step
    (CR 514.3) -- where the rules do hand it out if a trigger or a discard
    intervenes, which this engine cannot produce; see ``disclosure``.
    """
    holder = state.active_player if has_priority(state.step) else None
    return replace(state, priority=holder, passed=())


def acted(state: GameState, player_id: PlayerId) -> GameState:
    """Give priority back to the player who has just used it (CR 117.3c).

    And empty ``passed``: a pass counts only "in succession" with the passes
    beside it, and an action between two of them breaks the run (CR 117.4).
    Without that, a player could pass, cast, and have their own earlier pass
    still standing -- one more pass from the opponent and a spell they had just
    cast would resolve with nobody having had the chance to answer it.
    """
    return replace(state, priority=player_id, passed=())


def resolved(state: GameState) -> GameState:
    """Priority after something resolves: the active player (CR 117.3b).

    Not the spell's controller, which is the intuitive wrong answer: a spell
    the *nonactive* player answered with still hands priority back to the
    player whose turn it is.
    """
    return replace(state, priority=state.active_player, passed=())


def passes(state: GameState, player_id: PlayerId) -> GameState:
    """One player declines to act, and priority moves on (CR 117.3d).

    The next player in turn order receives it -- unless that was the last pass,
    in which case nobody holds it while the top of the stack resolves or the
    step ends (CR 117.4). Both of those are separate events here; this leaves
    the game in the one state from which they are legal.

    "The next player in turn order" is spelled as "the first who has not passed
    yet", which is the same player only because a game has exactly two of them
    (see ``state.PLAYER_COUNT``). A third would make them differ, and would
    need this line rewritten rather than merely re-read -- which is the reason
    it says so here instead of leaving a reader to work it out.

    Raises:
        IllegalEventError: If ``player_id`` does not hold priority. A device
            must not be able to pass on the other seat's behalf.
    """
    demanded(state, player_id)
    passed = (*state.passed, player_id)
    remaining = tuple(player for player in turn_order(state) if player not in passed)
    return replace(state, passed=passed, priority=remaining[0] if remaining else None)
