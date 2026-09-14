"""The check that retrieval still finds the rule each question is about.

Everything else in the rules package is checkable against the excerpt.
Retrieval is a *ranking* over three and a half thousand passages, and whether
the right one comes back depends on how common every word is in the whole
document -- so the check runs against the installed rules, and these run
against the check.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

import check_retrieval as gate
from helpers_rules import EXCERPT, PASSAGES
from mtgcoach.rules.search import RuleIndex

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture(scope="module")
def index() -> Generator[RuleIndex]:
    """The excerpt, indexed once."""
    with RuleIndex.build(PASSAGES) as built:
        yield built


def test_the_shipped_question_list_is_readable() -> None:
    """It is data, so nothing else would notice it going wrong."""
    questions = gate.asked(gate.QUESTIONS)
    assert len(questions) > 10
    for entry in questions:
        assert entry["ask"], entry
        assert entry["any"], entry


def test_the_shipped_list_names_its_known_gaps() -> None:
    """A gap is written down rather than deleted.

    That is what keeps the list honest about what is still broken.
    """
    gaps = [entry for entry in gate.asked(gate.QUESTIONS) if "gap" in entry]
    assert all(str(entry["gap"]).strip() for entry in gaps), "a gap needs its reason"


def test_a_file_with_no_questions_in_it_is_refused(tmp_path: Path) -> None:
    where = tmp_path / "q.json"
    where.write_text(json.dumps({"questions": []}), encoding="utf-8")
    with pytest.raises(ValueError, match="no question list"):
        gate.asked(where)


def test_a_file_that_is_not_an_object_is_refused(tmp_path: Path) -> None:
    where = tmp_path / "q.json"
    where.write_text(json.dumps(["ask me"]), encoding="utf-8")
    with pytest.raises(ValueError, match="no question list"):
        gate.asked(where)


def test_a_question_that_finds_its_rule_is_ok(index: RuleIndex) -> None:
    got = gate.verdicts(index, [{"ask": "what does deathtouch do?", "any": ["702.2a"]}])
    assert [state for state, _ask, _detail in got] == ["ok"]


def test_a_question_that_does_not_is_a_miss(index: RuleIndex) -> None:
    """And the failure says what was wanted and what came back.

    The next person to see it will be looking at a ranking they did not write.
    """
    got = gate.verdicts(index, [{"ask": "what does deathtouch do?", "any": ["999.9z"]}])
    (state, _ask, detail) = got[0]
    assert state == "miss"
    assert "999.9z" in detail
    assert "702.2a" in detail


def test_a_known_gap_that_is_still_missing_is_a_gap(index: RuleIndex) -> None:
    got = gate.verdicts(
        index, [{"ask": "what does deathtouch do?", "any": ["999.9z"], "gap": "not indexed"}]
    )
    assert [state for state, _ask, _detail in got] == ["gap"]


def test_a_known_gap_that_now_passes_is_reported(index: RuleIndex) -> None:
    """Otherwise the note outlives the problem and the list starts lying."""
    got = gate.verdicts(
        index, [{"ask": "what does deathtouch do?", "any": ["702.2a"], "gap": "was broken"}]
    )
    assert [state for state, _ask, _detail in got] == ["fixed"]


def test_a_question_with_no_acceptable_references_is_a_miss(index: RuleIndex) -> None:
    """A typo in the list must not read as a pass."""
    got = gate.verdicts(index, [{"ask": "what does deathtouch do?", "any": "702.2a"}])
    assert [state for state, _ask, _detail in got] == ["miss"]


@pytest.mark.parametrize(
    ("report", "code"),
    [
        ([("ok", "q", "")], 0),
        ([("gap", "q", "wanted x")], 0),
        ([("miss", "q", "wanted x")], 1),
        ([("fixed", "q", "was broken")], 1),
    ],
)
def test_the_exit_code_says_whether_the_list_needs_attention(
    report: list[tuple[str, str, str]], code: int, capsys: pytest.CaptureFixture[str]
) -> None:
    assert gate.said(report) == code
    assert "questions answered" in capsys.readouterr().out


def test_it_skips_loudly_when_the_rules_are_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    assert gate.main() == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_it_runs_against_an_installed_document(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The excerpt standing in for the real thing.

    With questions it can actually answer: the shipped list is written for the
    whole document.
    """
    _install(tmp_path, EXCERPT.read_text(encoding="utf-8"))
    asking = tmp_path / "q.json"
    asking.write_text(
        json.dumps({"questions": [{"ask": "what does deathtouch do?", "any": ["702.2a"]}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    monkeypatch.setattr(gate, "QUESTIONS", asking)
    assert gate.main() == 0
    assert "1/1 questions answered" in capsys.readouterr().out


def test_a_broken_question_list_is_a_failure_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The gate wants an exit code and a sentence, not a traceback."""
    _install(tmp_path, EXCERPT.read_text(encoding="utf-8"))
    broken = tmp_path / "q.json"
    broken.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    monkeypatch.setattr(gate, "QUESTIONS", broken)
    assert gate.main() == 1
    assert "could not run the retrieval check" in capsys.readouterr().out


def _install(data_root: Path, document: str) -> None:
    """Write a rules document where the checker will look for it."""
    where = data_root / "rules"
    where.mkdir(parents=True, exist_ok=True)
    (where / "comprehensive.txt").write_text(document, encoding="utf-8")
