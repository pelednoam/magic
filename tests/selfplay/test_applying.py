"""Turning a decision into the events the engine actually has.

The engine has no event for casting a spell, so a player casting a creature
does what the app's user does: taps the lands the payment names and moves the
card onto the battlefield. These check that this module does exactly that and
nothing cleverer -- a harness that invented rules would be testing itself.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from helpers_selfplay import BOOK, THEM, YOU, game, main_phase

from mtgcoach.coach.report import advise
from mtgcoach.core.combat.board import Outcome
from mtgcoach.core.combat.model import Creature
from mtgcoach.core.combat.search import Plan
from mtgcoach.core.reduce import replay
from mtgcoach.core.zones import ZoneName
from mtgcoach.selfplay.applying import attacked, played

if TYPE_CHECKING:
    from mtgcoach.coach.report import Playable
    from mtgcoach.core.ids import PlayerId
    from mtgcoach.core.state import GameState


def _playable(state: GameState, seat: PlayerId = YOU) -> Playable:
    """The first card the engine says can be played."""
    return advise(state, seat, BOOK).playable[0]


def test_a_land_is_played_with_the_land_drop() -> None:
    """Not `MoveCard`.

    The land drop is a limit and `PlayLand` is what spends it; a harness that
    moved the card instead would never exercise it.
    """
    state = main_phase()
    card = _playable(state)
    after = played(state, YOU, card).state
    assert after.player(YOU).lands_played_this_turn == 1
    assert card.instance_id in {p.instance_id for p in after.player(YOU).battlefield}


def test_casting_taps_the_sources_the_payment_named() -> None:
    """The engine says which lands pay; this taps those and no others."""
    with_lands = main_phase()
    # Two forests down and untapped, and a bear affordable.
    for _ in range(2):
        with_lands = played(with_lands, YOU, _playable(with_lands)).state
        with_lands = with_lands.with_player(
            YOU, replace(with_lands.player(YOU), lands_played_this_turn=0)
        )
    bear = next(card for card in advise(with_lands, YOU, BOOK).playable if not card.is_land)
    assert bear.payment is not None
    after = played(with_lands, YOU, bear).state
    tapped = {p.instance_id for p in after.player(YOU).battlefield if p.tapped}
    assert tapped == set(bear.payment.tapped)
    assert bear.instance_id in {p.instance_id for p in after.player(YOU).battlefield}


def test_an_attack_applies_the_engines_own_numbers() -> None:
    """Damage, then deaths, then life gained -- the order the rules use."""
    state = game()
    before = state.player(THEM).life
    plan = Plan(attackers=(), outcome=Outcome(damage_to_defender=3), defender_life_after=before - 3)
    after = attacked(state, YOU, plan).state
    assert after.player(THEM).life == before - 3


def test_the_creatures_an_attack_loses_go_to_the_graveyard() -> None:
    state = played(main_phase(), YOU, _playable(main_phase())).state
    permanent = state.player(YOU).battlefield[0]
    facts = BOOK.facts(permanent.card.oracle_id)
    assert facts is not None
    creature = Creature(permanent=permanent, card=facts)
    plan = Plan(
        attackers=(creature,),
        outcome=Outcome(attackers_lost=(creature,)),
        defender_life_after=state.player(THEM).life,
    )
    after = attacked(state, YOU, plan).state
    assert after.player(YOU).battlefield == ()
    assert permanent.card.instance_id in {c.instance_id for c in after.player(YOU).graveyard}


def test_lifelink_on_either_side_is_applied() -> None:
    """Life gained is tracked per side.

    A blocker with lifelink gains the *defender* life, which changes whether
    an attack was lethal at all.
    """
    state = game()
    mine, theirs = state.player(YOU).life, state.player(THEM).life
    plan = Plan(
        attackers=(),
        outcome=Outcome(attacker_life_gained=2, defender_life_gained=3),
        defender_life_after=theirs,
    )
    after = attacked(state, YOU, plan).state
    assert after.player(YOU).life == mine + 2
    assert after.player(THEM).life == theirs + 3


def test_an_attack_that_does_nothing_changes_nothing() -> None:
    state = game()
    plan = Plan(attackers=(), outcome=Outcome(), defender_life_after=state.player(THEM).life)
    assert attacked(state, YOU, plan).state.players == state.players


def test_a_card_moved_to_the_battlefield_is_a_permanent() -> None:
    """The zone a cast card goes to.

    Spelled out, because `MoveCard` would take any of them.
    """
    state = main_phase()
    after = played(state, YOU, _playable(state)).state
    assert after.player(YOU).zone(ZoneName.BATTLEFIELD)


def test_what_was_applied_comes_back_with_the_state() -> None:
    """The log is what makes a game replayable by anything holding `core`.

    The journal records it and the API rebuilds any moment from it, so the
    board a child is shown is what the events produced rather than a
    re-derivation a later engine change could alter.
    """
    state = main_phase()
    done = played(state, YOU, _playable(state))
    assert done.events, "a land drop is an event"
    assert replay(state, done.events) == done.state, "the log rebuilds the state exactly"


def test_an_attacks_whole_outcome_is_in_the_log() -> None:
    state = game()
    plan = Plan(
        attackers=(),
        outcome=Outcome(damage_to_defender=2, attacker_life_gained=1),
        defender_life_after=state.player(THEM).life - 2,
    )
    done = attacked(state, YOU, plan)
    assert len(done.events) == 2, "the damage and the lifelink"
    assert replay(state, done.events) == done.state
