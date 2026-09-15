"""Checks the engine cannot make for itself, made where the card data is.

``core`` is deliberately free of card data, and pays for it in one place: the
reducer cannot tell whether the card you are playing as your land is a land.
Its own docstring says so, and says the check "arrives with the card database".
This is where the card database arrives.

Everything here is a rule that needs to know what a card *is*. Anything that
needs only the state belongs in the reducer, where it cannot be skipped by a
caller who forgets to ask.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from mtgcoach.api.eventfields import BadEventError
from mtgcoach.coach import mana
from mtgcoach.core.events import CastSpell, PlayLand, ResolveSpell
from mtgcoach.core.legality import why_not_cast, why_not_play_land
from mtgcoach.core.zones import ZoneName

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.events import Event
    from mtgcoach.core.facts import CardFacts
    from mtgcoach.core.ids import InstanceId
    from mtgcoach.core.state import GameState


def check(event: Event, state: GameState, lookup: CardLookup) -> None:
    """Refuse an event the card data says is illegal.

    Raises:
        BadEventError: If the event is one the cards involved do not allow.
    """
    if isinstance(event, PlayLand):
        _check_land(event, state, lookup)
    elif isinstance(event, CastSpell):
        _check_cast(event, state, lookup)
    elif isinstance(event, ResolveSpell):
        _check_resolve(event, state, lookup)


def _check_land(event: PlayLand, state: GameState, lookup: CardLookup) -> None:
    """Refuse a land drop the coach has just said is illegal.

    Asks ``legality`` rather than re-deciding, which is the point. The first
    version checked only that the card was a land, and the reducer checks only
    hand membership and the land drop -- so nothing checked *timing*, and the
    server accepted a land played during the untap step while the advice in the
    very same response read "you can only play lands in a main phase". A server
    that contradicts its own coach is worse than one that is merely strict.

    A card the coach cannot *identify* is refused. That is a different thing
    from one whose abilities are unmodelled -- 59 of the box's cards are the
    second kind, they have facts, and they play normally. The first kind is a
    card the store has never seen, and nothing about it says "land": treating
    unknown as permitted reopened the hole this function exists to close.
    """
    hand = state.player(event.player).hand
    facts = _known(hand, event.instance_id, lookup, doing="play as a land")
    if facts is None:
        return
    _refuse(facts, why_not_play_land(state, event.player, facts))


def _check_cast(event: CastSpell, state: GameState, lookup: CardLookup) -> None:
    """Refuse a cast the coach has just said is illegal.

    The same argument as ``_check_land``, and the same shape: the reducer
    checks only that the card is in hand, so without this the server would
    accept a sorcery cast on the opponent's turn while the advice in the very
    same response read "you can only play this on your own turn".

    Asks ``why_not_cast``, which is the function the coach's own panel is built
    from -- timing, priority, sorcery speed, an empty stack, and whether the
    mana is actually there.
    """
    facts = _known(state.player(event.player).hand, event.instance_id, lookup, doing="cast")
    if facts is None:
        return
    sources = mana.available(state.player(event.player).battlefield, lookup)
    _refuse(facts, why_not_cast(state, event.player, facts, sources))


def _check_resolve(event: ResolveSpell, state: GameState, lookup: CardLookup) -> None:
    """Refuse a spell resolving to the wrong zone for what it is.

    The one check that keeps the oldest bug in this project from coming back
    from the other side of the wire. ``ResolveSpell`` takes its destination
    from the caller, because ``core`` cannot read a type line -- so a client
    that sent ``to: battlefield`` for an Opt would put an instant among the
    lands for the rest of the game, which is exactly what used to happen and
    exactly what a child would see.

    CR 608.3 for a permanent spell, CR 608.2m for an instant or a sorcery, and
    no third answer.
    """
    stack = state.player(event.player).stack
    facts = _known(stack, event.instance_id, lookup, doing="resolve")
    if facts is None:
        return
    belongs = ZoneName.BATTLEFIELD if facts.is_permanent else ZoneName.GRAVEYARD
    if event.to is not belongs:
        kind = "a permanent spell" if facts.is_permanent else "an instant or a sorcery"
        msg = (
            f"{facts.name} is {kind}, so it resolves to the "
            f"{belongs.value}, not to the {event.to.value}"
        )
        raise BadEventError(msg)


def _known(
    zone: Sequence[CardInstance],
    instance_id: InstanceId,
    lookup: CardLookup,
    doing: str,
) -> CardFacts | None:
    """What the card data says about this card, or None if it is not there.

    None means the card is not in the zone the event needs it in. The reducer
    will say so too, and better, so it is left to it.

    A card the coach cannot *identify* is a different thing and is refused: no
    facts means the store has never seen it, or its cost would not parse -- not
    that its *abilities* are unmodelled, which is a separate question with a
    separate answer (``modelled``). Nothing about an unknown card says it is a
    land, or an instant, and treating unknown as permitted is what reopened
    this hole the first time.

    Raises:
        BadEventError: If the card is there and the coach cannot name it.
    """
    card = next((one for one in zone if one.instance_id == instance_id), None)
    if card is None:
        return None
    facts = lookup.facts(card.oracle_id)
    if facts is None:
        msg = f"{card.oracle_id}: the coach does not know this card, so it cannot {doing} it"
        raise BadEventError(msg)
    return facts


def _refuse(facts: CardFacts, reasons: Sequence[str]) -> None:
    """Turn the coach's first objection into the server's refusal.

    The coach's own words, because it is the coach's own check: a server that
    contradicts the advice in the very same response is worse than one that is
    merely strict.

    Raises:
        BadEventError: If there is anything wrong with it.
    """
    if reasons:
        msg = f"{facts.name}: {reasons[0]}"
        raise BadEventError(msg)
