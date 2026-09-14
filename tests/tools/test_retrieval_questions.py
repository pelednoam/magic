"""The question list itself: what counts as a question, and what does not.

Split from `test_check_retrieval`, which is about asking them. These are about
the file -- a malformed entry used to be filtered out silently, so a bad edit
could cost coverage without anything saying so, and an entry that was only a
`gap` note was reported as an allowed gap without ever being asked.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

import check_retrieval as gate

if TYPE_CHECKING:
    from pathlib import Path


@pytest.mark.parametrize(
    ("entry", "complaint"),
    [
        ("not an object", "not an object"),
        ({"any": ["509.1a"]}, "has no 'ask'"),
        ({"ask": "  ", "any": ["509.1a"]}, "has no 'ask'"),
        ({"ask": "can a tapped creature block?"}, "has no 'any'"),
        ({"ask": "can a tapped creature block?", "any": []}, "has no 'any'"),
        ({"ask": "can a tapped creature block?", "any": "509.1a"}, "has no 'any'"),
        ({"gap": "broken data"}, "has no 'ask'"),
    ],
)
def test_a_malformed_question_is_refused_rather_than_dropped(
    tmp_path: Path, entry: object, complaint: str
) -> None:
    """They used to be filtered out with `isinstance(entry, dict)`.

    A bad edit or a JSON transform could therefore cost coverage in silence --
    and an entry that was only `{"gap": "..."}` was reported as an allowed gap,
    which is a way of marking a question known-broken without ever asking it.
    """
    where = tmp_path / "q.json"
    where.write_text(json.dumps({"questions": [entry]}), encoding="utf-8")
    with pytest.raises(ValueError, match=complaint):
        gate.asked(where)


def test_asking_nothing_is_not_a_pass(capsys: pytest.CaptureFixture[str]) -> None:
    """A gate that asked nothing must not report a pass.

    Reporting 0/0 and exiting 0 is indistinguishable from a green run, and
    every way of getting there is a way of losing the check.
    """
    assert gate.said([]) == 1
    assert "no questions were asked" in capsys.readouterr().out
