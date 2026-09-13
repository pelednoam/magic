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

from mtgcoach.core.manasolver import payments
from mtgcoach.core.player import MAX_LAND_DROPS_PER_TURN
from mtgcoach.core.steps import is_main_phase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.manacost import ManaSource
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.state import GameState


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
    if not card.is_instant_speed:
        reasons.extend(_sorcery_timing(state, player_id, "this"))
    if not payments(card.cost, sources):
        reasons.append(_mana_shortfall(card, sources))
    return tuple(reasons)


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
    available = len(sources)
    needed = card.cost.total
    if available < needed:
        short = needed - available
        return f"you need {short} more untapped source{'s' if short > 1 else ''}"
    missing = sorted(
        colour
        for colour in card.cost.colors
        if not any(colour in source.produces for source in sources)
    )
    if missing:
        return f"you have no source of {'/'.join(missing)}"
    return "your untapped sources cannot cover that combination of colours"


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
