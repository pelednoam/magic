"""What must be true after every single event, whatever anybody played.

This is where the value of self-play is. A thousand games played badly by a
policy that does not understand Magic will still put the engine through states
no test fixture would think of -- and the way to notice is not to check the
*play*, which is allowed to be foolish, but to check the things no play may
ever break.

Every check below is a sentence from the engine's own documentation. Card
conservation is named in ``PlayerState.cards`` as "the basis of the
conservation invariant: no event may change how many cards this yields";
``InstanceId`` exists so that "the Mountain you tapped" is distinguishable from
the other one; the land drop is a limit the reducer enforces. They are checked
here because a self-play game applies thousands of events in an order nobody
chose, which is exactly when an invariant that holds in every test stops
holding.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING

from mtgcoach.core.priority import all_passed
from mtgcoach.core.steps import TURN_ORDER, has_priority, named

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.core.state import GameState

#: A life total outside this is not a game any more. Wide on purpose: the point
#: is to catch arithmetic that has run away, not to have an opinion about how
#: much life a player may gain.
SANE_LIFE = range(-1000, 1001)

#: One land per turn. The reducer enforces it; this catches an event applied by
#: a path that went around the reducer.
LAND_DROPS = 1


def broken(before: GameState, after: GameState) -> Iterator[str]:
    """Everything that is wrong with this transition, in words.

    Takes the state on both sides because the most valuable invariant is a
    *conservation*: the question is not whether there are 60 cards but whether
    there are as many as there were a moment ago. A single state cannot answer
    that, and a harness that only checked the end of a game would learn which
    game broke and never which event.
    """
    yield from _conserved(before, after)
    yield from _distinct(after)
    yield from _sane(after)


def _conserved(before: GameState, after: GameState) -> Iterator[str]:
    """Cards do not appear or vanish.

    Asked of ``GameState.cards_of`` rather than ``PlayerState.cards``, which is
    what it used to be. The stack is one shared, ordered field now, so a
    player's cards live in two objects and only the game state can compose
    them -- and the invariant is stronger for it: a spell mis-attributed on the
    stack, or dropped while resolving out of order, changes this count, and a
    season checks it on every one of a hundred thousand events.
    """
    for player_id in before.players:
        had = Counter(card.instance_id for card in before.cards_of(player_id))
        has = Counter(card.instance_id for card in after.cards_of(player_id))
        if had.total() != has.total():
            yield f"{player_id} had {had.total()} cards and now has {has.total()}"
        lost = had - has
        if lost:
            yield f"{player_id} lost track of {sorted(lost)[:4]}"


def _distinct(state: GameState) -> Iterator[str]:
    """No card is in two places, and no two cards are the same card."""
    seen = Counter(card.instance_id for card in state.cards())
    twice = [instance for instance, count in seen.items() if count > 1]
    if twice:
        yield f"{len(twice)} card(s) in two places at once: {sorted(twice)[:4]}"


def _sane(state: GameState) -> Iterator[str]:
    """The fields that have a range have not left it."""
    if state.turn < 1:
        yield f"turn {state.turn}"
    if state.step not in TURN_ORDER:
        yield f"step {state.step!r} is not a step"
    for player_id, player in state.players.items():
        if player.life not in SANE_LIFE:
            yield f"{player_id} is on {player.life} life"
        if player.lands_played_this_turn > LAND_DROPS:
            yield f"{player_id} has played {player.lands_played_this_turn} lands this turn"
    yield from _priority(state)


def _priority(state: GameState) -> Iterator[str]:
    """Priority is somebody's, or nobody's, and only for a real reason.

    Things no play may break. Priority belongs to a player who is in the game
    -- a holder who is not is a seat nobody can ever act from. Nobody holds it
    in the untap or cleanup steps (CR 502.4, CR 514.3), and *somebody* holds it
    in every other step, unless everybody has passed: a step that handed it to
    nobody is a game that has stopped, where no event is legal and no step can
    end. And a player cannot pass twice without acting in between, because a
    pass counts only in succession (CR 117.4) -- a duplicate would resolve a
    spell one player had never had the chance to answer.
    """
    holder = state.priority
    if holder is not None and holder not in state.players:
        yield f"{holder} holds priority and is not in the game"
    if holder is not None and not has_priority(state.step):
        yield f"{holder} holds priority during the {named(state.step)}"
    if holder is None and has_priority(state.step) and not all_passed(state):
        # Somebody has to be able to act. A step that hands out priority and
        # gave it to nobody, with nobody having passed, is a game that has
        # simply stopped -- no event is legal and no step can end.
        yield f"nobody holds priority during the {named(state.step)}"
    if len(set(state.passed)) != len(state.passed):
        yield f"{sorted(state.passed)} has a player passing twice in succession"
    if len(state.passed) > len(state.players):
        yield f"{len(state.passed)} passes from {len(state.players)} players"
    for one in state.stack:
        if one.controller not in state.players:
            yield f"{one.instance_id} on the stack is controlled by nobody in the game"
