"""The agents themselves: the policy, the idle one, and the coach.

The policy is not graded on how well it plays -- it does not understand Magic,
and the harness watches invariants rather than results. What it must do is
keep producing moves the engine offered, whatever the board.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from helpers_selfplay import BOOK, YOU, game, main_phase

from helpers import ME, facts
from helpers_coach import Book
from helpers_coach import game as board
from mtgcoach.coach.advice import ExplainerError, Explanation
from mtgcoach.coach.report import advise
from mtgcoach.core.steps import Step
from mtgcoach.selfplay.coached import Coached
from mtgcoach.selfplay.moves import Idle, Move
from mtgcoach.selfplay.policy import Greedy

if TYPE_CHECKING:
    from mtgcoach.coach.report import TurnReport

#: A board with something on it, for the one test that needs an attack.
COMBAT = Book(cards={"Bear": facts("Grizzly Bears", power=2, toughness=2, creature=True)})


@dataclass(frozen=True, slots=True)
class Saying:
    """An explainer that answers with whatever it was built with."""

    said: Explanation | None = None

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """The answer, or a refusal.

        Raises:
            ExplainerError: When built with nothing to say.
        """
        del report, briefing
        if self.said is None:
            msg = "the coach took longer than 90s"
            raise ExplainerError(msg)
        return self.said


def test_the_idle_agent_does_nothing_ever() -> None:
    state = game()
    assert Idle().act(state, advise(state, YOU, BOOK), YOU) == Move()


def test_the_policy_plays_a_land_when_it_has_one() -> None:
    """Lands first, always.

    A policy that spends its main phase on a one-drop and never makes its land
    drop stalls on two mana forever, and a board that never grows never
    reaches the interesting states.
    """
    state = main_phase()
    report = advise(state, YOU, BOOK)
    lands = {card.instance_id for card in report.playable if card.is_land}
    played = {Greedy(seed=seed).act(state, report, YOU).play for seed in range(20)}
    assert played - {None} <= lands


def test_the_policy_only_ever_names_something_the_engine_offered() -> None:
    """The one property the harness needs from it."""
    state = main_phase()
    report = advise(state, YOU, BOOK)
    offered = {card.instance_id for card in report.playable}
    for seed in range(50):
        move = Greedy(seed=seed).act(state, report, YOU)
        assert move.play is None or move.play in offered


def test_the_policy_sometimes_does_nothing() -> None:
    """Keeps hands from emptying at the same rate in every game."""
    state = main_phase()
    report = advise(state, YOU, BOOK)
    assert any(Greedy(seed=seed).act(state, report, YOU).play is None for seed in range(40))


def test_the_same_seed_plays_the_same_way() -> None:
    """A season that finds something can be replayed exactly."""
    state = main_phase()
    report = advise(state, YOU, BOOK)
    assert Greedy(seed=3).act(state, report, YOU) == Greedy(seed=3).act(state, report, YOU)


def test_the_coach_plays_what_it_recommends() -> None:
    state = main_phase()
    report = advise(state, YOU, BOOK)
    card = report.playable[0]
    agent = Coached(
        explainer=Saying(
            Explanation(play=str(card.instance_id), because="a land", in_short="a land")
        )
    )
    assert agent.act(state, report, YOU).play == card.instance_id
    assert agent.tally.trusted == 1


def test_the_coach_does_not_play_advice_that_failed_its_checks() -> None:
    """The same rule the server applies on a player's behalf.

    A harness that played unchecked advice would be measuring something nobody
    is ever shown.
    """
    state = main_phase()
    report = advise(state, YOU, BOOK)
    agent = Coached(
        explainer=Saying(Explanation(play="not-in-hand", because="why", in_short="why"))
    )
    assert agent.act(state, report, YOU) == Move()
    assert agent.tally.untrusted == 1
    assert agent.tally.disagreements


def test_the_coach_having_no_answer_is_recorded_and_survived() -> None:
    state = main_phase()
    report = advise(state, YOU, BOOK)
    agent = Coached(explainer=Saying(None))
    assert agent.act(state, report, YOU) == Move()
    assert agent.tally.refused == 1
    assert "no answer" in agent.tally.disagreements[0]


def test_the_tally_adds_up() -> None:
    state = main_phase()
    report = advise(state, YOU, BOOK)
    agent = Coached(explainer=Saying(None))
    for _ in range(3):
        agent.act(state, report, YOU)
    assert agent.tally.asked == 3
    assert agent.tally.trusted == 0


def test_the_policy_attacks_when_the_engine_offers_one() -> None:
    """Combat is the half of the engine most worth exercising.

    The policy takes whatever the engine ranked first, because ranking attacks
    is the engine's job and second-guessing it here would be this module
    having an opinion about Magic.
    """
    state = board(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS)
    report = advise(state, ME, COMBAT)
    assert report.attacks.plans, "the fixture is meant to offer an attack"
    best = report.attacks.plans[0]
    attacked = [Greedy(seed=seed).act(state, report, ME).attack for seed in range(30)]
    wanted = tuple(creature.instance_id for creature in best.attackers)
    assert wanted in attacked, "it should usually take the best plan"
    assert () in attacked, "and sometimes hold back"
