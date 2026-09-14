"""Every decision written down, so a coached game can be run again.

A seed reproduces a deal exactly -- the engine generates no randomness. It does
not reproduce the coach, which is a language model and will answer differently
tomorrow. So these are about the one thing that makes a coached game
repeatable: keeping what it said.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mtgcoach.coach.advice import Explanation
from mtgcoach.selfplay.journal import Decision, Journal, explanation, fields, read

if TYPE_CHECKING:
    from pathlib import Path

SAID = Explanation(
    play="you-3",
    attack=("you-1", "you-2"),
    because="it trades up",
    in_short="yours is bigger",
    watch_out=("they have a card in hand",),
    check_yourself=("Pacifism",),
)

MADE = Decision(
    seed=7,
    turn=4,
    step="precombat_main",
    player="you",
    briefing="YOUR HAND: ...",
    answer=fields(SAID),
    trusted=True,
)


def test_a_decision_knows_which_moment_it_is() -> None:
    """Keyed by moment rather than order.

    Replaying in order would misalign silently the instant a game diverged.
    """
    assert MADE.moment == (7, 4, "precombat_main", "you")


def test_a_decision_survives_the_round_trip(tmp_path: Path) -> None:
    where = tmp_path / "run.jsonl"
    Journal(where).write(MADE)
    back = read(where)
    assert len(back) == 1
    found = back.at(MADE.moment)
    assert found is not None
    assert found == MADE


def test_the_answer_survives_it_too(tmp_path: Path) -> None:
    """Every field, because a replay applies the whole thing."""
    where = tmp_path / "run.jsonl"
    Journal(where).write(MADE)
    found = read(where).at(MADE.moment)
    assert found is not None
    assert found.answer is not None
    assert explanation(found.answer) == SAID


def test_the_briefing_is_kept(tmp_path: Path) -> None:
    """Large, and worth every byte.

    A disagreement is only diagnosable next to the board the model was shown.
    """
    where = tmp_path / "run.jsonl"
    Journal(where).write(MADE)
    found = read(where).at(MADE.moment)
    assert found is not None
    assert found.briefing == "YOUR HAND: ..."


def test_decisions_are_appended_not_replaced(tmp_path: Path) -> None:
    """A run interrupted at three in the morning keeps what it had."""
    where = tmp_path / "run.jsonl"
    journal = Journal(where)
    journal.write(MADE)
    journal.write(Decision(seed=7, turn=5, step="declare_attackers", player="them", briefing=""))
    assert len(read(where)) == 2


def test_a_missing_directory_is_made(tmp_path: Path) -> None:
    where = tmp_path / "deep" / "down" / "run.jsonl"
    Journal(where).write(MADE)
    assert where.is_file()


def test_a_refusal_is_recorded_as_one(tmp_path: Path) -> None:
    where = tmp_path / "run.jsonl"
    Journal(where).write(
        Decision(seed=1, turn=1, step="untap", player="you", briefing="", error="timed out")
    )
    found = read(where).at((1, 1, "untap", "you"))
    assert found is not None
    assert found.answer is None
    assert found.error == "timed out"


def test_a_half_written_last_line_does_not_lose_the_rest(tmp_path: Path) -> None:
    """A journal is written by a process that may have been killed mid-write.

    Losing the last line of a three-hour run is not a reason to refuse the
    other four hundred.
    """
    where = tmp_path / "run.jsonl"
    Journal(where).write(MADE)
    with where.open("a", encoding="utf-8") as file:
        file.write('{"seed": 7, "turn": 5, "step": "dr')
    assert len(read(where)) == 1


def test_lines_that_are_not_decisions_are_skipped(tmp_path: Path) -> None:
    where = tmp_path / "run.jsonl"
    where.write_text(
        "\n".join(
            [
                "",
                "   ",
                "[1, 2]",
                json.dumps({"turn": 1, "step": "untap", "player": "you"}),
                json.dumps({"seed": 1, "step": "untap", "player": "you"}),
                json.dumps({"seed": 1, "turn": 1, "player": "you"}),
                json.dumps({"seed": 1, "turn": 1, "step": "untap"}),
                MADE.as_json(),
            ]
        ),
        encoding="utf-8",
    )
    assert len(read(where)) == 1


def test_an_answer_of_the_wrong_shape_reads_as_no_answer(tmp_path: Path) -> None:
    where = tmp_path / "run.jsonl"
    where.write_text(
        json.dumps(
            {
                "seed": 1,
                "turn": 1,
                "step": "untap",
                "player": "you",
                "answer": "a string",
                "problems": "not a list",
            }
        ),
        encoding="utf-8",
    )
    found = read(where).at((1, 1, "untap", "you"))
    assert found is not None
    assert found.answer is None
    assert found.problems == ()


def test_an_explanation_with_nothing_in_it_still_reads() -> None:
    """A model that answered with an empty object is a real case."""
    assert explanation({}) == Explanation()


def test_a_list_field_that_is_not_a_list_reads_as_empty() -> None:
    assert explanation({"attack": "you-1"}).attack == ()


def test_a_moment_the_journal_does_not_have_is_none(tmp_path: Path) -> None:
    where = tmp_path / "run.jsonl"
    Journal(where).write(MADE)
    assert read(where).at((99, 99, "untap", "you")) is None
