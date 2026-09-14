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
    """A reply carrying ``fields``, plus the keys every reply must have.

    ``play`` and ``attack`` are in here because the prompt demands them and the
    parser now refuses a reply without them -- see ``fields._missing``. A test
    about one field should not have to think about the other two, and a test
    *about* an absent key builds its payload itself.
    """
    return json.dumps({"because": "because.", "play": "", "attack": [], **fields})


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


def test_a_missing_prose_field_is_an_empty_one() -> None:
    """Prose only.

    A missing `play` or `attack` is refused rather than read as "nothing" --
    `test_a_reply_missing_a_demanded_key_is_refused` covers that.
    """
    got = parse(envelope(json.dumps({"because": "No good options.", "play": "", "attack": []})))
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


@pytest.mark.parametrize(
    ("payload", "missing"),
    [
        ({"because": "Wait.", "attack": []}, "play"),
        ({"because": "Wait.", "play": ""}, "attack"),
        ({"because": "Wait."}, "play"),
    ],
)
def test_a_reply_missing_a_demanded_key_is_refused(
    payload: dict[str, object], missing: str
) -> None:
    """Silence is not a recommendation.

    Read as one it became an explicit "play nothing, attack with nobody",
    which the engine agrees with whenever holding back is right -- so it came
    back `trusted`, and the screen said so in the coach's voice. The prompt
    asks for both keys.
    """
    with pytest.raises(ExplainerError, match=f"'{missing}' was not"):
        parse(envelope(json.dumps(payload)))


def test_an_empty_string_in_a_prose_list_is_dropped() -> None:
    assert parse(said(watch_out=["", "real"])).watch_out == ("real",)
