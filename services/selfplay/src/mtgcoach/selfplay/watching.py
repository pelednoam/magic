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

from mtgcoach.core.steps import TURN_ORDER

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
    """Cards do not appear or vanish."""
    for player_id, was in before.players.items():
        now = after.player(player_id)
        had, has = sum(1 for _ in was.cards()), sum(1 for _ in now.cards())
        if had != has:
            yield f"{player_id} had {had} cards and now has {has}"
        lost = Counter(card.instance_id for card in was.cards()) - Counter(
            card.instance_id for card in now.cards()
        )
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
