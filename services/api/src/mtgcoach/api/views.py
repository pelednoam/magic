"""The JSON the client sees, written out by hand.

Not a serialisation of the engine's types. A ``Creature`` carries a
``Permanent`` carrying a ``CardInstance``, and a ``CardFacts`` carrying a parsed
``ManaCost``; dumping that would put the engine's shape on the wire and make
every refactor a client change. §4 says the app is a deliberately dumb view, and
this is the contract that keeps it able to be one.

So each function here is a small, explicit translation, and the cost of it is
the point: adding a field to the wire is a decision someone makes, not something
that happens.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence

    from mtgcoach.coach.advice import Explanation
    from mtgcoach.coach.attacks import Attacks
    from mtgcoach.coach.report import Playable, TurnReport
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.combat.search import Plan
    from mtgcoach.core.ids import OracleId
    from mtgcoach.core.manasolver import Payment
    from mtgcoach.core.permanents import Permanent
    from mtgcoach.core.player import PlayerState
    from mtgcoach.core.state import GameState
    from mtgcoach.core.triggerscan import Reminder

#: What a JSON value can be, once it has been built. Deliberately concrete:
#: ``object`` would let anything through and ``Any`` is banned outright.
#:
#: ``Sequence`` and ``Mapping`` rather than ``list`` and ``dict`` because both of
#: those are invariant: a plain ``list[str]`` is not a ``list[Json]``, and every
#: route would have had to build its lists the long way round to say so.
type Json = str | int | bool | Sequence["Json"] | Mapping[str, "Json"] | None

#: How the views ask for a card's printed name. A function rather than a dict so
#: a caller can back it with the store without loading the whole set first.
type Naming = Callable[["OracleId"], str]


def report(turn: TurnReport) -> dict[str, Json]:
    """A whole turn's advice."""
    return {
        "turn": turn.turn,
        "step": turn.step.value,
        "your_turn": turn.your_turn,
        "life": turn.life,
        "hand": [playable(card) for card in turn.hand],
        "attacks": attacks(turn.attacks),
        "reminders": [reminder(r) for r in turn.reminders],
        "unknown": list(turn.unknown),
    }


def explanation(advice: Explanation) -> dict[str, Json]:
    """What the coach said, once the engine has agreed with it."""
    return {
        "play": advice.play,
        "attack": list(advice.attack),
        "because": advice.because,
        "in_short": advice.in_short,
        "watch_out": list(advice.watch_out),
        "check_yourself": list(advice.check_yourself),
    }


def playable(card: Playable) -> dict[str, Json]:
    """One card in hand, and the verdict on it."""
    return {
        "instance_id": str(card.instance_id),
        "name": card.name,
        "is_land": card.is_land,
        "playable": card.playable,
        "reasons": list(card.reasons),
        "payment": payment(card.payment) if card.payment is not None else None,
    }


def payment(paid: Payment) -> dict[str, Json]:
    """Which lands to tap, and -- the useful half -- which to keep up."""
    return {
        "tap": [str(source) for source in paid.tapped],
        "keep": [str(source) for source in paid.spare],
    }


def attacks(options: Attacks) -> dict[str, Json]:
    """The attacks worth making, or the sentence saying why there are none."""
    return {
        "unavailable": options.unavailable,
        "caveats": list(options.caveats),
        "plans": [plan(option) for option in options.plans],
    }


def plan(option: Plan) -> dict[str, Json]:
    """One attack and what the opponent's best answer does to it."""
    return {
        # Both: the names are what a player reads, the ids are what a client
        # can key a list on. Names alone re-introduced at the wire the identity
        # collapse ``core.Outcome`` documents as a bug -- two Grizzly Bears are
        # two creatures, and a playset is the ordinary case.
        "attackers": list(option.names),
        "attacker_ids": [str(c.instance_id) for c in option.attackers],
        "damage": option.outcome.damage_to_defender,
        "defender_life_after": option.defender_life_after,
        "lethal": option.is_lethal,
        "you_lose": list(option.outcome.attacker_names),
        "they_lose": list(option.outcome.blocker_names),
        "you_gain": option.outcome.attacker_life_gained,
        "they_gain": option.outcome.defender_life_gained,
    }


def reminder(trigger: Reminder) -> dict[str, Json]:
    """A trigger the player is about to miss."""
    return {
        "instance_id": str(trigger.instance_id),
        "name": trigger.name,
        "event": trigger.event.value,
    }


def state(game: GameState, names: Naming) -> dict[str, Json]:
    """The board, as much of it as a client may see.

    Every player's *library* is a count, never a list. A tracker that shows you
    the top of your own deck is a cheating tool, and one that shows your
    opponent's is a worse one -- §3's non-goals put both out of scope.

    ``names`` is passed in because the state does not know them: ``core`` holds
    no card data, and a client should not have to ask twice for the word printed
    on the card in front of it.
    """
    return {
        "turn": game.turn,
        "step": game.step.value,
        "active_player": str(game.active_player),
        "players": {str(pid): _player(player, names) for pid, player in game.players.items()},
    }


def _player(player: PlayerState, names: Naming) -> dict[str, Json]:
    """One player's half of the board."""
    return {
        "life": player.life,
        "library": len(player.library),
        "lands_played_this_turn": player.lands_played_this_turn,
        "hand": [_card(card, names) for card in player.hand],
        "battlefield": [_permanent(p, names) for p in player.battlefield],
        "graveyard": [_card(card, names) for card in player.graveyard],
        "exile": [_card(card, names) for card in player.exile],
    }


def _card(card: CardInstance, names: Naming) -> dict[str, Json]:
    """One card, by all three of the things a client needs to call it."""
    return {
        "instance_id": str(card.instance_id),
        "oracle_id": str(card.oracle_id),
        "name": names(card.oracle_id),
    }


def _permanent(permanent: Permanent, names: Naming) -> dict[str, Json]:
    """One permanent, with the two states a tracker has to show."""
    return {
        **_card(permanent.card, names),
        "tapped": permanent.tapped,
        "summoning_sick": permanent.summoning_sick,
    }
