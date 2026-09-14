"""Getting an object out of what the command printed.

Two envelopes deep: the CLI wraps the model's reply in its own JSON, and the
reply is itself JSON. Both are unwrapped defensively, because the failure mode
that matters is a model answering in prose -- which is a thing to report, not a
thing to guess the meaning of.

Shared by the turn coach and the rules answerer. Neither decides anything with
what comes out; the checkers in ``coach.advice`` and ``rules.answer`` do that.
Reading the individual fields out of the object is ``fields``.
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
    or a code fence. It is a fallback rather than the first move so that a
    reply which is valid JSON but the *wrong* JSON -- an array of options, say
    -- is reported as the wrong shape instead of being quietly reinterpreted.

    Scanned rather than sliced. Taking the first ``{`` to the last ``}`` broke
    on anything with another brace in it -- a sentence mentioning ``{T}``, or
    the CLI printing a second object after the reply -- which is not an exotic
    case when the subject is Magic and mana symbols are written in braces.

    Raises:
        ExplainerError: If neither attempt finds JSON.
    """
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        pass
    found = _objects_in(body)
    if not found:
        # Deliberately without the body. This message reaches the client and
        # the CORS policy is `*`; `body` is the CLI's raw stdout when the
        # envelope could not be read, and a CLI that prints a usage or auth
        # error there carries absolute paths and config locations with it.
        msg = "the coach did not answer with an object"
        raise ExplainerError(msg)
    # The largest, which is the reply rather than a fragment quoted beside it.
    return max(found, key=_span)[1]


def _span(found: tuple[int, object]) -> int:
    """How many characters an object took up. ``len`` measured the pair."""
    return found[0]


def _objects_in(body: str) -> list[tuple[int, object]]:
    """Every complete JSON object in ``body``, as (length, value).

    ``raw_decode`` from each ``{`` in turn: it stops at the end of the value it
    read, so a brace that opens nothing costs one failed parse rather than
    swallowing the rest of the text.
    """
    decoder = json.JSONDecoder()
    found: list[tuple[int, object]] = []
    at = body.find("{")
    while at >= 0:
        try:
            value, end = decoder.raw_decode(body, at)
        except (json.JSONDecodeError, ValueError):
            at = body.find("{", at + 1)
            continue
        found.append((end - at, value))
        at = body.find("{", end)
    return found


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
