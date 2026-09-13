"""Reading a batch of proposals back out of a model's reply.

Separated from the subprocess call so that parsing can be tested against
recorded replies -- no model, no network, no waiting -- which is most of what
there is to get wrong here.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from mtgcoach.carddata.abilitycodec import decode
from mtgcoach.carddata.extraction import Confidence, Proposal
from mtgcoach.carddata.jsondata import (
    MalformedJsonError,
    as_array,
    as_object,
    optional_str,
    require_str,
)
from mtgcoach.core.ids import OracleId

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.carddata.cards import Card
    from mtgcoach.core.abilities import Ability


def omissions(
    asked: Sequence[Card], got: Sequence[Proposal], attempted: set[str] | None = None
) -> list[str]:
    """Report cards the model was given but said nothing about.

    A malformed proposal is already reported as a rejection; counting it again
    here as "missing" made 22 problems look like 44 and hid that nothing was
    actually absent. ``attempted`` is every name the reply mentioned, whether or
    not it survived decoding.

    Silence is still not agreement: a card the model simply skipped is reported.
    """
    answered = {p.name for p in got} | (attempted or set())
    return [f"{card.name}: no proposal returned" for card in asked if card.name not in answered]


def _strip_fence(text: str) -> str:
    body = text.strip()
    if body.startswith("```"):
        body = body.split("\n", 1)[-1]
        body = body.rsplit("```", 1)[0]
    return body.strip()


def parse_response(
    stdout: str, cards: Sequence[Card]
) -> tuple[list[Proposal], list[str], set[str]]:
    """Read the CLI envelope, the proposals inside it, and every name it mentioned.

    A card whose proposal does not validate is reported and skipped rather than
    failing its whole batch -- the same lesson as importing a bulk file, where
    one odd card must not cost the other nine.

    Raises:
        MalformedJsonError: If the envelope itself cannot be read, which means
            nothing in the batch can be trusted.
    """
    envelope = as_object(json.loads(stdout))
    if envelope is None:
        msg = "claude did not return a JSON envelope"
        raise MalformedJsonError(msg)
    if envelope.get("is_error") is True:
        msg = f"claude reported an error: {optional_str(envelope, 'result')[:200]}"
        raise MalformedJsonError(msg)

    body = as_array(json.loads(_strip_fence(require_str(envelope, "result", "claude"))))
    if body is None:
        msg = "the model did not return a JSON array"
        raise MalformedJsonError(msg)

    by_name = {c.name: c for c in cards}
    proposals: list[Proposal] = []
    failures: list[str] = []
    attempted: set[str] = set()
    for item in body:
        named = as_object(item)
        if named is not None:
            attempted.add(optional_str(named, "name"))
        try:
            proposals.append(_proposal(item, by_name))
        except MalformedJsonError as exc:
            failures.append(str(exc))
    return proposals, failures, attempted


def _proposal(item: object, by_name: dict[str, Card]) -> Proposal:
    obj = as_object(item)
    if obj is None:
        msg = "a proposal is not an object"
        raise MalformedJsonError(msg)
    name = require_str(obj, "name", "proposal")
    card = by_name.get(name)
    if card is None:
        msg = f"proposal names a card that was not asked about: {name!r}"
        raise MalformedJsonError(msg)

    raw = as_array(obj.get("abilities")) or []
    abilities: list[Ability] = [decode(a, name) for a in raw]
    confidence = optional_str(obj, "confidence", "low")
    try:
        level = Confidence(confidence)
    except ValueError as exc:
        msg = f"{name}: unknown confidence {confidence!r}"
        raise MalformedJsonError(msg) from exc
    return Proposal(
        oracle_id=OracleId(card.oracle_id),
        name=name,
        abilities=tuple(abilities),
        confidence=level,
        notes=optional_str(obj, "notes"),
    )
