"""Output that is not an answer, and must not become one.

The split from ``test_explainer`` is by what the reply *is*: that module reads
well-formed replies and fields of the wrong shape, this one covers the outputs
that carry no answer at all -- an apology, a list of options, the CLI's own
error envelope. None of them may reach a player as advice, and none of them may
reach one as a traceback either.
"""

from __future__ import annotations

import json

import pytest

from mtgcoach.api.explainer import parse
from mtgcoach.coach.advice import ExplainerError
from test_explainer import ANSWER, envelope


def test_prose_with_no_object_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="did not answer with an object"):
        parse(envelope("I'm sorry, I can't help with that."))


def test_empty_output_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="did not answer with an object"):
        parse("")


def test_a_broken_object_is_an_error() -> None:
    with pytest.raises(ExplainerError, match="did not answer with an object"):
        parse(envelope('{"play": "abc", }'))


def test_a_brace_in_the_prose_does_not_break_the_parse() -> None:
    """Not exotic when the subject is Magic: mana symbols are written {G}.

    Taking the first `{` to the last `}` made every answer that mentioned one
    unreadable, which is most answers about paying for anything.
    """
    said = json.dumps({**ANSWER, "because": "Tap the Forest for {G}."})
    assert parse(envelope(f"Here you go:\n{said}\nHope that helps.")).play == "abc"


def test_the_answer_is_the_largest_object_not_the_first() -> None:
    """A model quoting a fragment before its answer used to win the race."""
    said = json.dumps(ANSWER)
    assert parse(envelope(f'{{"note": "x"}} {said}')).play == "abc"


def test_a_json_value_that_is_not_an_object_is_an_error() -> None:
    """A model that answers with a list of options has not chosen one."""
    with pytest.raises(ExplainerError, match="not an object"):
        parse(envelope('["attack", "hold"]'))


def test_an_answer_with_no_words_in_it_is_an_error() -> None:
    """A choice with nothing said about it.

    Reached when the reply carries both demanded keys and no prose at all.
    Blank on screen would look like the coach had considered the board and had
    nothing to say.
    """
    with pytest.raises(ExplainerError, match="no explanation in it"):
        parse(json.dumps({"play": "", "attack": []}))


def test_the_clis_own_error_envelope_is_an_error() -> None:
    """Its `result` is null.

    That decodes to a well-formed object with none of the fields in it, so the
    first demanded key is the one that catches it.
    """
    with pytest.raises(ExplainerError, match="'play' was not"):
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
    reply = '[1, 2] {"play": "abc", "attack": [], "because": "why"}'
    assert parse(reply).play == "abc"


def test_output_that_is_json_but_not_an_envelope_is_read_as_the_answer() -> None:
    """A bare array is not a CLI envelope, and is not an answer either."""
    with pytest.raises(ExplainerError, match="not an object"):
        parse('["attack", "hold"]')
