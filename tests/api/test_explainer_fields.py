"""The two fields a checker will compare against the engine.

Everything else in a reply is prose, and a malformed sentence costs a sentence.
These two are claims: an attack is matched against the plans the engine costed,
and a citation against the passages the server retrieved. Trimming a bad
element out of either does not lose information, it changes the claim -- and
changes it towards passing. So they are all-or-nothing, and these say so.
"""

from __future__ import annotations

import pytest

from mtgcoach.api.explainer import parse
from mtgcoach.coach.advice import ExplainerError
from test_explainer import said


def test_a_malformed_attack_is_refused_rather_than_trimmed() -> None:
    """Trimming changes the claim, and changes it towards passing.

    ["bear-1", 7] trimmed to ["bear-1"] is a *different attack* -- one the
    engine did cost -- so the checker would then agree with a recommendation
    nobody made.
    """
    with pytest.raises(ExplainerError, match="'attack' was not a list"):
        parse(said(attack=["bear-1", 7]))


def test_an_attack_that_is_not_a_list_is_refused() -> None:
    with pytest.raises(ExplainerError, match="'attack' was not a list"):
        parse(said(attack="bear-1"))


def test_an_empty_string_in_an_attack_is_refused() -> None:
    """An empty instance id matches nothing and would read as "attack with"."""
    with pytest.raises(ExplainerError, match="'attack' was not a list"):
        parse(said(attack=["bear-1", ""]))


def test_a_missing_attack_is_simply_no_attack() -> None:
    """Absent and malformed are different: absent is the common case."""
    assert parse(said()).attack == ()


@pytest.mark.parametrize("field", ["play", "attack"])
def test_an_explicit_null_is_malformed_rather_than_none(field: str) -> None:
    """The schema asks for a string and a list; `null` is neither.

    Through `.get` the two were indistinguishable, so a model answering
    off-schema got a do-nothing recommendation -- which is a real choice, and
    one that passes.
    """
    with pytest.raises(ExplainerError, match=f"'{field}' was not"):
        parse(said(**{field: None}))


def test_prose_lists_are_still_trimmed_rather_than_refused() -> None:
    """Nothing is checked against these, so a dropped sentence costs a sentence."""
    got = parse(said(watch_out=["real", 7, ""], check_yourself=["Pacifism"]))
    assert got.watch_out == ("real",)
    assert got.check_yourself == ("Pacifism",)


@pytest.mark.parametrize("bad", [42, ["abc"], {"id": "abc"}])
def test_a_play_that_is_not_a_string_is_refused(bad: object) -> None:
    """Empty means "play nothing", which is a real recommendation.

    So turning a malformed value into empty does not lose information -- it
    substitutes a different recommendation, and one that always passes.
    """
    with pytest.raises(ExplainerError, match="'play' was not"):
        parse(said(play=bad))
