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

from mtgcoach.core.manashortfall import mana_shortfall
from mtgcoach.core.manasolver import can_pay
from mtgcoach.core.player import MAX_LAND_DROPS_PER_TURN
from mtgcoach.core.priority import lacking
from mtgcoach.core.steps import Step, is_main_phase

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.manacost import ManaSource
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.state import GameState


def why_not_play_land(state: GameState, player_id: PlayerId, card: CardFacts) -> tuple[str, ...]:
    """Reasons this land cannot be played now, empty when it can.

    All of CR 116.2a, which is the rule for the special action rather than
    CR 305.1's summary of it: a land drop is your turn, your main phase, an
    empty stack -- and priority. The priority half is last because the other
    three explain themselves better when they apply; the case it is the only
    answer to is the one where you have already passed.
    """
    reasons: list[str] = []
    if not card.is_land:
        reasons.append(f"{card.name} is not a land")
    reasons.extend(_sorcery_timing(state, player_id, "lands"))
    player = state.player(player_id)
    if player.lands_played_this_turn >= MAX_LAND_DROPS_PER_TURN:
        reasons.append("you have already played a land this turn")
    reasons.extend(lacking(state, player_id))
    return tuple(reasons)


def why_not_cast(
    state: GameState,
    player_id: PlayerId,
    card: CardFacts,
    sources: Sequence[ManaSource],
) -> tuple[str, ...]:
    """Reasons this card cannot be cast now, empty when it can.

    Raises:
        IllegalEventError: If ``player_id`` is not in this game.
        DuplicateSourceError: If two sources share an identity -- one permanent
            cannot be tapped twice.
        TooManySourcesError: If there are more untapped sources than the mana
            solver will search exactly.

    The last two are deliberately exceptions rather than reasons. A reason is
    something the player can act on ("you need one more Forest"); these say the
    *question* was malformed or too large, which is the caller's problem and not
    the player's, and quietly returning "you can't cast that" would be a lie.
    """
    reasons: list[str] = []
    # Raises for an unknown player, as every other predicate here does. An
    # instant used to skip every state lookup, so a bad id came back "castable".
    state.player(player_id)
    if card.is_land:
        reasons.append("lands are played, not cast")
    if not card.cost.is_payable:
        # CR 202.1a: no printed mana cost means no way to cast it. Not the same
        # as costing {0}, which both parsed identically until they were split.
        reasons.append(f"{card.name} has no mana cost, so it cannot be cast")
    # CR 117.1a's first clause, and the one this used to answer only half of.
    # It asked whether the *step* hands out priority (CR 502.4, 514.3) -- so an
    # instant read as castable during untap, where nobody may do anything at
    # all. It could not ask whether *you* have it, because nothing recorded a
    # holder. ``lacking`` answers both, in one wording the reducer refuses with
    # too, so the server cannot contradict this advice in the same response.
    reasons.extend(lacking(state, player_id))
    if not card.is_instant_speed:
        reasons.extend(_sorcery_timing(state, player_id, "this"))
    if not can_pay(card.cost, sources):
        reasons.append(mana_shortfall(card, sources))
    return tuple(reasons)


def _sorcery_timing(state: GameState, player_id: PlayerId, subject: str) -> tuple[str, ...]:
    """Sorcery speed: your turn, your main phase, nothing on the stack.

    All three of CR 117.1a. The empty-stack half used to be missing with a note
    saying it "arrives with casting, and this is the site that will need it" --
    casting has arrived, so here it is: a spell waiting to resolve means it is
    not your turn to act at sorcery speed, however much it looks like your main
    phase.

    The whole stack, and there is only one of it now. This used to add up a
    tuple per player, with a note that a spell your opponent cast is on the
    stack exactly as much as one of yours -- true, and the arithmetic was the
    shape of a zone that had no single order. One field says the same thing and
    can also say which spell resolves first.
    """
    if state.active_player != player_id:
        return (f"you can only play {subject} on your own turn",)
    if not is_main_phase(state.step):
        return (f"you can only play {subject} in a main phase",)
    if state.stack:
        return (f"you can only play {subject} when nothing is waiting to resolve",)
    return ()


def can_play_land(state: GameState, player_id: PlayerId, card: CardFacts) -> bool:
    """Whether this land can be played now."""
    return not why_not_play_land(state, player_id, card)


def can_cast(
    state: GameState,
    player_id: PlayerId,
    card: CardFacts,
    sources: Sequence[ManaSource],
) -> bool:
    """Whether this card can be cast now.

    Raises:
        IllegalEventError: If ``player_id`` is not in this game.
        DuplicateSourceError: If two sources share an identity.
        TooManySourcesError: If there are too many sources to search exactly.
    """
    return not why_not_cast(state, player_id, card, sources)


def why_not_declare_attackers(state: GameState, player_id: PlayerId) -> tuple[str, ...]:
    """Reasons no attack can be declared right now, empty when one can.

    Separate from ``why_not_attack`` because they are separate questions with
    separate answers. This one is about the clock -- CR 508.1a, your own
    declare-attackers step -- and is asked once; the other is about a creature,
    and is asked once per creature. A caller that asked only the second got a
    confident "yes, Grizzly Bears can attack" during its controller's upkeep.

    ``Permanent`` carries no controller, which is why the player is a separate
    argument rather than read off the creature.

    Raises:
        IllegalEventError: If ``player_id`` is not in this game. Comparing it
            against the active player alone answered "not your turn" for a name
            that was never playing.
    """
    state.player(player_id)
    if state.active_player != player_id:
        return ("you can only attack on your own turn",)
    if state.step is not Step.DECLARE_ATTACKERS:
        return ("attackers are declared in the declare attackers step",)
    return ()


def can_declare_attackers(state: GameState, player_id: PlayerId) -> bool:
    """Whether an attack can be declared right now."""
    return not why_not_declare_attackers(state, player_id)


def why_not_attack(permanent: Permanent, card: CardFacts) -> tuple[str, ...]:
    """Reasons this *creature* cannot attack, empty when it can.

    Timing is not checked here -- see ``why_not_declare_attackers``, which the
    coach asks once for the whole attack rather than once per creature.

    Vigilance is not checked either: it governs whether attacking *taps* the
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
    """Whether this creature could be declared as an attacker."""
    return not why_not_attack(permanent, card)
