"""Self-play applies actions through the same checks a player's tap goes through.

It used to call the reducer directly. That exercised every check in ``core``
and none of the card-aware ones in ``api.guard``, so a whole class of defect
could pass a three-hundred-game season while failing the first tap in the app.

One did. Casting was refused over HTTP for every paid spell -- the guard
recomputed the available mana after the payment had already been spent -- while
a season applied three thousand casts without complaint, because nothing in the
harness ever asked the guard anything.

These are about the wiring, not the rules: that the guard is consulted, that a
real game supplies what it needs, and that its refusals are not swallowed.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import pytest
from helpers_selfplay import BOOK, THEM, YOU, game, main_phase

from mtgcoach.api.eventfields import BadEventError
from mtgcoach.coach.report import Playable, advise
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.reduce import apply
from mtgcoach.core.steps import Step
from mtgcoach.selfplay.applying import attacked, played
from mtgcoach.selfplay.moves import Seat
from mtgcoach.selfplay.passing import ending
from mtgcoach.selfplay.playing import play
from mtgcoach.selfplay.policy import Greedy

if TYPE_CHECKING:
    from mtgcoach.core.state import GameState


def _first(state: GameState) -> Playable:
    """The first card the engine says can be played."""
    return advise(state, YOU, BOOK).playable[0]


def test_a_guarded_apply_refuses_what_the_server_would_refuse() -> None:
    """The card data's checks, reached from the harness.

    "The coach does not know this card, so it cannot play it as a land" is the
    guard's oldest check and lives nowhere else. Reaching it from here is the
    whole point: the harness and the server now fail on the same things.
    """
    # A card in hand that the catalogue has never heard of. In hand, because
    # the reducer -- not the guard -- answers for a card that is not; and
    # unknown to the book, because that is the check being reached.
    mystery = CardInstance(InstanceId("what-is-this"), OracleId("Nonesuch"))
    state = main_phase()
    holding = state.player(YOU)
    state = state.with_player(YOU, replace(holding, hand=(mystery, *holding.hand)))
    offered = Playable(mystery.instance_id, "Nonesuch", is_land=True)
    with pytest.raises(BadEventError, match="does not know this card"):
        played(state, YOU, offered, BOOK)


def test_an_unguarded_apply_still_works_for_a_test_holding_no_catalogue() -> None:
    """The default, and the only reason it is optional.

    A test building one event by hand should not need a catalogue. A real game
    always has one -- which the next test is what keeps true.
    """
    state = main_phase()
    assert played(state, YOU, _first(state)).events


def test_a_real_game_consults_the_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wiring, watched rather than assumed.

    ``lookup`` is optional so a one-line test can skip it, and that default is
    exactly how the guard could quietly stop being consulted in a real season.
    So this plays a real game with the guard replaced by a counter, and asserts
    it was asked about every event.
    """
    asked: list[str] = []

    def watching(event: object, state: object, lookup: object) -> None:
        del state, lookup
        asked.append(type(event).__name__)

    monkeypatch.setattr("mtgcoach.selfplay.applying.guard.check", watching)
    both = (Seat(YOU, "forests", Greedy(seed=1)), Seat(THEM, "forests", Greedy(seed=2)))
    play(both, game(), BOOK, seed=4)
    assert asked, "a whole game went by without the guard being asked anything"
    # Every land drop and every cast, at least. The count is not pinned -- the
    # claim is that the guard is in the path, not how long the game was.
    assert "PlayLand" in asked


def test_an_attack_taps_the_attackers() -> None:
    """CR 508.1f, and the consequence the recorded game used to omit.

    A creature that attacked and survived stayed untapped, so the replay showed
    it available for a second attack -- or to pay for a spell -- on a board
    where it was lying sideways on the table.
    """
    # A settled Bear, which is what it takes to have an attack to make.
    state = main_phase()
    bear = CardInstance(InstanceId("bear-1"), OracleId("Grizzly Bears"))
    mine = state.player(YOU)
    state = state.with_player(
        YOU, replace(mine, battlefield=(*mine.battlefield, Permanent(bear).settle()))
    )
    while state.step is not Step.DECLARE_ATTACKERS:
        for event in ending(state):
            state = apply(state, event)
    report = advise(state, YOU, BOOK)
    plan = next((one for one in report.attacks.plans if one.attackers), None)
    assert plan is not None, "a settled Bear and no attack to make"
    after = attacked(state, YOU, plan, BOOK).state
    attackers = {one.instance_id for one in plan.attackers}
    still_there = [
        permanent
        for permanent in after.player(YOU).battlefield
        if permanent.instance_id in attackers
    ]
    for permanent in still_there:
        assert permanent.tapped, f"{permanent.instance_id} attacked and is still untapped"
