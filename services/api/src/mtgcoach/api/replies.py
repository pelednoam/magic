"""Getting an object out of what the command printed.

Two envelopes deep: the CLI wraps the model's reply in its own JSON, and the
reply is itself JSON. Both are unwrapped defensively, because the failure mode
that matters is a model answering in prose -- which is a thing to report, not a
thing to guess the meaning of.

Shared by the turn coach and the rules answerer. Neither decides anything with
what comes out; the checkers in ``coach.advice`` and ``rules.answer`` do that.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import ExplainerError

if TYPE_CHECKING:
    from collections.abc import Mapping


def object_in(stdout: str) -> Mapping[str, object]:
    """The JSON object in the command's output.

    Two envelopes deep: the CLI wraps the model's reply in its own JSON, and the
    reply is itself JSON. Both are unwrapped defensively, because the failure
    mode that matters is a model answering in prose -- which is a thing to
    report, not a thing to guess the meaning of.

    Raises:
        ExplainerError: If there is no object in there.
    """
    payload = _decode(_unwrap(stdout))
    if not isinstance(payload, dict):
        msg = "the coach answered with something that is not an object"
        raise ExplainerError(msg)
    # `json.loads` gives back an unparameterised dict, and strict pyright will
    # not let one through untyped. The cast states what the isinstance above
    # has already established; every field is then checked one at a time.
    return cast("Mapping[str, object]", payload)


def _decode(body: str) -> object:
    """The JSON value in ``body``, whole if it is all JSON, else the object in it.

    The second attempt is what survives a model that wraps its answer in prose
    or a code fence. It is a fallback rather than the first move so that a reply
    which is valid JSON but the *wrong* JSON -- an array of options, say -- is
    reported as the wrong shape instead of being quietly reinterpreted.

    Raises:
        ExplainerError: If neither attempt finds JSON.
    """
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        msg = f"the coach did not answer with an object: {body[:160]!r}"
        raise ExplainerError(msg)
    try:
        return json.loads(body[start : end + 1])
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"the coach's answer was not readable: {exc}"
        raise ExplainerError(msg) from exc


def _unwrap(stdout: str) -> str:
    """The model's reply, out of the CLI's envelope.

    Raises:
        ExplainerError: If the envelope says the run failed. Its ``result`` is
            then an error message, and an error message can contain braces --
            which the object scanner would happily mine for a reply that the
            model never wrote.
    """
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return stdout
    if not isinstance(envelope, dict):
        return stdout
    fields = cast("Mapping[str, object]", envelope)
    if fields.get("is_error") is True:
        msg = "the coach reported an error instead of an answer"
        raise ExplainerError(msg)
    result = fields.get("result")
    return result if isinstance(result, str) else stdout


def text(payload: Mapping[str, object], field: str) -> str:
    """A string field, empty when it is missing or the wrong type."""
    value = payload.get(field)
    return value if isinstance(value, str) else ""


def words(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    """A list of prose, keeping only the strings.

    For fields nothing is checked against: ``watch_out``, ``check_yourself``. A
    missing or malformed one is empty rather than an error, because a dropped
    sentence costs a sentence. Use ``exactly`` for anything a checker will then
    compare against the engine.
    """
    value = payload.get(field)
    if not isinstance(value, list):
        return ()
    items = cast("list[object]", value)
    return tuple(item for item in items if isinstance(item, str) and item)


def exactly(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    """A list of identifiers, all of them or none.

    For the fields a checker compares against the engine: ``attack``,
    ``citations``. Dropping a bad element from one of those does not lose a
    sentence, it changes the claim -- and changes it towards passing. An
    ``attack`` of ``["bear-1", 7]`` trimmed to ``["bear-1"]`` becomes a
    *different attack*, one the engine did cost, and the checker then agrees
    with a recommendation nobody made. Citations behave the same way in
    reverse: drop the invented one and what is left is all real.

    So a malformed element fails the whole field. The caller turns that into an
    ``ExplainerError`` and the player gets the engine's own panel, which is
    what they would have got from a refused answer anyway.

    Raises:
        MalformedFieldError: If the field is present and is not a list of
            non-empty strings.
    """
    value = payload.get(field)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise MalformedFieldError(field, value)
    items = cast("list[object]", value)
    if not all(isinstance(item, str) and item for item in items):
        raise MalformedFieldError(field, items)
    return tuple(cast("list[str]", items))


class MalformedFieldError(ExplainerError):
    """A field a checker would have compared against the engine is not usable."""

    def __init__(self, field: str, value: object) -> None:
        """Name the field and what arrived instead."""
        super().__init__(f"the coach's {field!r} was not a list of identifiers: {value!r:.80}")
