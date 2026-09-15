"""What priority and the stack do to "can I play this?".

Split from ``test_legality`` at the line limit, and the seam is a real one:
that file is about a *card* -- is it a land, does the mana cover it -- and this
one is about the *moment*. All three halves of CR 117.1a live here, and two of
them had nothing to check them with until the engine recorded who may act.

The old versions of these tests stopped where the engine did. "An instant can
be cast on the opponent's turn" asserted that it could be cast during their
upkeep before they had done anything, because the only question the engine
could ask was whether the *step* hands out priority to somebody. The moment a
beginner has to learn is the one that was missing: you get to hold the trick
when they pass.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from helpers import ME, YOU, at_step, deck, facts
from mtgcoach.core.events import CastSpell, PassPriority
from mtgcoach.core.ids import InstanceId
from mtgcoach.core.legality import can_cast, why_not_cast
from mtgcoach.core.manacost import ManaSource
from mtgcoach.core.reduce import apply
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step

if TYPE_CHECKING:
    from mtgcoach.core.ids import PlayerId

FOREST = ManaSource(InstanceId("forest"), frozenset("G"))
GIANT_GROWTH = facts("Giant Growth", "{G}", instant=True)


def _game(
    step: Step = Step.PRECOMBAT_MAIN, active: PlayerId = ME, holder: PlayerId | None = None
) -> GameState:
    """A board at one step, with priority handed out the way the step hands it.

    Its own copy rather than imported from ``test_legality``: a test module
    importing a sibling works under pytest and not under mypy, which is a seam
    not worth having for three lines.
    """
    game = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    return at_step(game, step, active, holder)


def test_an_instant_can_be_cast_on_the_opponents_turn() -> None:
    """Once you have priority, which on their turn means once they have passed.

    CR 117.1a is "any time they have priority", and the active player gets it
    first (CR 117.3a). This test used to say only "on their turn", because
    that was as much of the rule as the engine could check -- and the moment a
    beginner has to learn is exactly the one it skipped.
    """
    assert can_cast(_game(Step.UPKEEP, YOU, holder=ME), ME, GIANT_GROWTH, [FOREST])


def test_an_instant_is_not_castable_while_they_still_hold_priority() -> None:
    """The other half of the same rule, and the one that had no answer."""
    reasons = why_not_cast(_game(Step.UPKEEP, YOU), ME, GIANT_GROWTH, [FOREST])
    assert "you do not have priority right now" in reasons


def _waiting(state: GameState, caster: PlayerId) -> GameState:
    """The same board with one spell on the stack, cast by ``caster``.

    Casting takes priority to do and hands it straight back (CR 117.1a,
    CR 117.3c), so the caster is handed it first and is left holding it -- a
    test about the *other* player's options passes afterwards, which is what
    puts priority where CR 117.3d puts it.
    """
    holding = replace(state, priority=caster, passed=())
    return apply(holding, CastSpell(caster, state.player(caster).hand[0].instance_id))


def test_a_spell_waiting_to_resolve_stops_sorcery_speed() -> None:
    """The third half of CR 117.1a, which had no stack to look at until now.

    A spell waiting to resolve means it is not your turn to act at sorcery
    speed, however much it looks like your main phase.
    """
    main = _game()
    # A creature a single Forest pays for, so nothing but the stack is in the
    # way and the difference between the two calls is only the waiting spell.
    bear = facts("Bear", "{G}", creature=True, power=1, toughness=1)
    assert can_cast(main, ME, bear, [FOREST])
    reasons = why_not_cast(_waiting(main, ME), ME, bear, [FOREST])
    assert reasons == ("you can only play this when nothing is waiting to resolve",)


def test_the_opponents_spell_stops_it_too() -> None:
    """Sorcery timing asks whether *the* stack is empty, not whether yours is.

    The stack is one zone (CR 405.1) and one field here now, so there is no
    "your own half" left to look at only -- which is what let you cast a
    creature in response to theirs, the one thing sorcery speed forbids.
    """
    bear = facts("Bear", "{G}", creature=True, power=1, toughness=1)
    reasons = why_not_cast(_theirs_waiting(), ME, bear, [FOREST])
    assert reasons == ("you can only play this when nothing is waiting to resolve",)


def test_an_instant_is_unaffected_by_a_waiting_spell() -> None:
    """Which is what instant speed *is*: answering something on the stack."""
    assert can_cast(_theirs_waiting(), ME, GIANT_GROWTH, [FOREST])


def _theirs_waiting() -> GameState:
    """Your main phase, their spell on the stack, and your turn to answer it.

    The whole sequence, because every step of it is a rule: they can only cast
    while holding priority (CR 117.1a), they keep it afterwards (CR 117.3c),
    and it comes to you when they pass (CR 117.3d). Skipping to "a spell is on
    the stack and it is your turn to act" would be assuming the two events
    this engine exists to stop assuming.
    """
    return apply(_waiting(_game(), YOU), PassPriority(YOU))
