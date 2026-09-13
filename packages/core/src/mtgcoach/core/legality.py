"""What you may do right now, and -- when you may not -- why.

The second half is the point. "You can't cast that" teaches nothing; "you need
one more Forest" and "that's a sorcery, so only in your main phase" are the two
sentences a beginner needs most, and they are the two a rules engine usually
throws away on its way to a boolean.

So every predicate here is built on a function returning *reasons*, and the
boolean is the empty-reasons case rather than the other way round.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.core.manasolver import can_pay
from mtgcoach.core.player import MAX_LAND_DROPS_PER_TURN
from mtgcoach.core.steps import has_priority, is_main_phase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.manacost import ManaSource
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.state import GameState
    from mtgcoach.core.steps import Step


def why_not_play_land(state: GameState, player_id: PlayerId, card: CardFacts) -> tuple[str, ...]:
    """Reasons this land cannot be played now, empty when it can."""
    reasons: list[str] = []
    if not card.is_land:
        reasons.append(f"{card.name} is not a land")
    reasons.extend(_sorcery_timing(state, player_id, "lands"))
    player = state.player(player_id)
    if player.lands_played_this_turn >= MAX_LAND_DROPS_PER_TURN:
        reasons.append("you have already played a land this turn")
    return tuple(reasons)


def why_not_cast(
    state: GameState,
    player_id: PlayerId,
    card: CardFacts,
    sources: Sequence[ManaSource],
) -> tuple[str, ...]:
    """Reasons this card cannot be cast now, empty when it can."""
    reasons: list[str] = []
    if card.is_land:
        reasons.append("lands are played, not cast")
    if not has_priority(state.step):
        # CR 502.4, 514.3. Without this an instant reads as castable during
        # untap, where nobody may do anything at all -- the one step where even
        # "hold your Giant Growth" is wrong advice.
        reasons.append(f"nobody gets priority during the {_step_name(state.step)}")
    elif not card.is_instant_speed:
        reasons.extend(_sorcery_timing(state, player_id, "this"))
    if not can_pay(card.cost, sources):
        reasons.append(_mana_shortfall(card, sources))
    return tuple(reasons)


def _step_name(step: Step) -> str:
    """The step, as a player would say it."""
    return f"{step.value.replace('_', ' ')} step"


def _sorcery_timing(state: GameState, player_id: PlayerId, subject: str) -> tuple[str, ...]:
    """Sorcery speed: your turn, your main phase.

    CR 117.1a also requires an empty stack. That check is absent because the
    state has no stack yet -- nothing can put an object on one until spells can
    be cast, and a field no event can change is a field no test can cover. It
    arrives with casting, and this is the site that will need it.
    """
    if state.active_player != player_id:
        return (f"you can only play {subject} on your own turn",)
    if not is_main_phase(state.step):
        return (f"you can only play {subject} in a main phase",)
    return ()


def _mana_shortfall(card: CardFacts, sources: Sequence[ManaSource]) -> str:
    """Say what is missing, not merely that something is.

    Distinguishing "one short" from "no green at all" is the difference between
    a player waiting a turn and a player reading the wrong lesson.
    """
    if card.cost.colorless:
        # The solver refuses {C} outright, so every later branch would invent a
        # colour story for a cost that has nothing to do with colours.
        return "that needs colourless mana, which nothing here makes"
    available = len(sources)
    needed = card.cost.total
    if available < needed:
        short = needed - available
        return f"you need {short} more untapped source{'s' if short > 1 else ''}"
    missing = sorted(
        colour
        for colour in _required_colours(card)
        if not any(colour in source.produces for source in sources)
    )
    if missing:
        return f"you have no source of {'/'.join(missing)}"
    return "your untapped sources cannot cover that combination of colours"


def _required_colours(card: CardFacts) -> frozenset[str]:
    """The colours the cost genuinely demands.

    Not ``ManaCost.colors``, which unions a hybrid symbol's alternatives: for
    ``{W/U}{G}`` that set is ``{W, U, G}``, and a player holding a Plains and a
    Forest would be told they have no source of U. A hybrid symbol demands
    nothing in particular, so only single-colour symbols count.
    """
    return frozenset(next(iter(symbol)) for symbol in card.cost.symbols if len(symbol) == 1)


def can_play_land(state: GameState, player_id: PlayerId, card: CardFacts) -> bool:
    """Whether this land can be played now."""
    return not why_not_play_land(state, player_id, card)


def can_cast(
    state: GameState,
    player_id: PlayerId,
    card: CardFacts,
    sources: Sequence[ManaSource],
) -> bool:
    """Whether this card can be cast now."""
    return not why_not_cast(state, player_id, card, sources)


def why_not_attack(permanent: Permanent, card: CardFacts) -> tuple[str, ...]:
    """Reasons this creature cannot attack, empty when it can.

    Vigilance is not checked here: it governs whether attacking *taps* the
    creature (CR 702.20b), not whether it may attack.
    """
    reasons: list[str] = []
    if not card.is_creature:
        reasons.append(f"{card.name} is not a creature")
    if permanent.tapped:
        reasons.append(f"{card.name} is tapped")
    if permanent.summoning_sick and not card.has("Haste"):
        reasons.append(f"{card.name} has not been under your control since your turn began")
    if card.has("Defender"):
        reasons.append(f"{card.name} has defender")
    return tuple(reasons)


def can_attack(permanent: Permanent, card: CardFacts) -> bool:
    """Whether this creature can be declared as an attacker."""
    return not why_not_attack(permanent, card)
