"""Reading what the coach said, including when it said something useless.

The parsing here is the boundary between a language model and a program, and
every test below is a shape a model has actually produced somewhere: prose
around the JSON, a field of the wrong type, an apology instead of an answer.
None of them may become an exception the player sees, and none of them may
become advice either -- ``advice.verify`` gets the last word, but it can only
check an object, so this has to produce one or fail cleanly.
"""

from __future__ import annotations

import json

import pytest

from helpers import ME, facts
from helpers_coach import Book, game, land
from mtgcoach.api.explainer import parse
from mtgcoach.coach.advice import ExplainerError, Explanation
from mtgcoach.coach.report import advise

ANSWER = {
    "play": "abc",
    "attack": ["def"],
    "because": "It trades up.",
    "in_short": "Yours is bigger.",
    "watch_out": ["They have one card in hand."],
    "check_yourself": ["Pacifism"],
}


FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR},
    rules={"Forest": FOREST_RULES, "Bear": ()},
)
#: A turn with a decision in it, so the explainer actually asks.
REPORT = advise(game(hand=("Forest",)), ME, BOOK)


def envelope(result: str) -> str:
    """What the CLI prints around the model's reply."""
    return json.dumps({"type": "result", "result": result, "total_cost_usd": 0.0})


def said(**fields: object) -> str:
    """A reply carrying ``fields``, plus the words every reply must have."""
    return json.dumps({"because": "because.", **fields})


# --- parsing what came back ---------------------------------------------------


def test_reads_the_agreed_object() -> None:
    got = parse(envelope(json.dumps(ANSWER)))
    assert got == Explanation(
        play="abc",
        attack=("def",),
        because="It trades up.",
        in_short="Yours is bigger.",
        watch_out=("They have one card in hand.",),
        check_yourself=("Pacifism",),
    )


def test_reads_a_bare_object_without_the_clienvelope() -> None:
    """Useful in a test, and the shape `--output-format text` would give."""
    assert parse(json.dumps(ANSWER)).play == "abc"


def test_ignores_prose_around_the_object() -> None:
    wrapped = "Sure! Here's my advice:\n```json\n" + json.dumps(ANSWER) + "\n```\nHope that helps."
    assert parse(envelope(wrapped)).in_short == "Yours is bigger."


def test_a_missing_field_is_an_empty_one() -> None:
    got = parse(envelope(json.dumps({"because": "No good options."})))
    assert got.because == "No good options."
    assert got.play == ""
    assert got.attack == ()
    assert got.watch_out == ()


def test_an_empty_recommendation_survives() -> None:
    """Play nothing and attack with nobody is advice, not an absence of it."""
    got = parse(envelope(json.dumps({"play": "", "attack": [], "in_short": "Wait."})))
    assert got.play == ""
    assert got.attack == ()
    assert got.in_short == "Wait."


# --- fields of the wrong shape ------------------------------------------------


def test_a_null_play_is_simply_no_card() -> None:
    """Absent and malformed are different: absent is the common case."""
    assert parse(said(play=None)).play == ""


def test_an_empty_string_in_a_prose_list_is_dropped() -> None:
    assert parse(said(watch_out=["", "real"])).watch_out == ("real",)


# --- answers that are not answers ---------------------------------------------


def test_prose_with_no_object_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="did not answer with an object"):
        parse(envelope("I'm sorry, I can't help with that."))


def test_empty_output_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="did not answer with an object"):
        parse("")


def test_a_broken_object_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="not readable"):
        parse(envelope('{"play": "abc", }'))


def test_two_objects_side_by_side_are_an_error() -> None:
    """The brace slice spans both, which is not readable -- and must not be."""
    with pytest.raises(ExplainerError, match="not readable"):
        parse(envelope('{"play": "abc"} {"play": "xyz"}'))


def test_a_json_value_that_is_not_an_object_is_an_error() -> None:
    """A model that answers with a list of options has not chosen one."""
    with pytest.raises(ExplainerError, match="not an object"):
        parse(envelope('["attack", "hold"]'))


def test_an_answer_with_no_words_in_it_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="no explanation in it"):
        parse(json.dumps({"type": "result", "result": None}))


def test_an_envelope_that_says_it_failed_is_an_error() -> None:
    """Its `result` is an error message, and error messages contain braces.

    Without this the object scanner mined the message for something
    brace-shaped and returned it as the model's reply.
    """
    failed = {"type": "result", "is_error": True, "result": 'failed at {"x": 1}'}
    with pytest.raises(ExplainerError, match="reported an error"):
        parse(json.dumps(failed))


def test_an_answer_that_is_only_a_choice_is_an_error() -> None:
    """A choice with no reasoning teaches nothing, which is the whole point."""
    with pytest.raises(ExplainerError, match="no explanation in it"):
        parse(envelope(json.dumps({"play": "abc", "attack": ["def"]})))


def test_output_that_is_not_whole_json_falls_through_to_the_object_in_it() -> None:
    assert parse('[1, 2] {"play": "abc", "because": "why"}').play == "abc"


def test_output_that_is_json_but_not_an_envelope_is_read_as_the_answer() -> None:
    """A bare array is not a CLI envelope, and is not an answer either."""
    with pytest.raises(ExplainerError, match="not an object"):
        parse('["attack", "hold"]')
