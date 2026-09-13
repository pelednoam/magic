"""Reading a model's reply, including the replies that go wrong.

Driven from recorded envelopes rather than a live call, which is where nearly
all the risk in this path actually sits.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from mtgcoach.carddata.extraction import Confidence
from mtgcoach.carddata.jsondata import MalformedJsonError
from mtgcoach.carddata.proposals import omissions, parse_response
from mtgcoach.carddata.scryfall import cards_in

if TYPE_CHECKING:
    from mtgcoach.carddata.cards import Card

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"

MANA_ABILITY = {
    "kind": "activated",
    "cost": {"mana": "", "tap": True, "sacrifice_self": False},
    "effects": [{"kind": "produce_mana", "mana": "{G}", "amount": 1}],
}


def _cards() -> list[Card]:
    return list(cards_in(FIXTURE))


def _envelope(result: object, *, is_error: bool = False) -> str:
    """A Claude CLI reply envelope, as the real command emits one."""
    body = result if isinstance(result, str) else json.dumps(result)
    return json.dumps({"is_error": is_error, "result": body})


def _reply(name: str, **extra: object) -> dict[str, object]:
    return {
        "name": name,
        "confidence": "high",
        "notes": "",
        "abilities": [MANA_ABILITY],
        **extra,
    }


def test_a_well_formed_reply() -> None:
    cards = _cards()
    got, bad, attempted = parse_response(_envelope([_reply(cards[0].name)]), cards)
    assert bad == []
    assert attempted == {cards[0].name}
    assert got[0].name == cards[0].name
    assert got[0].confidence is Confidence.HIGH
    assert len(got[0].abilities) == 1


def test_a_fenced_reply_is_unwrapped() -> None:
    """Models fence JSON even when told not to."""
    cards = _cards()
    fenced = "```json\n" + json.dumps([_reply(cards[0].name)]) + "\n```"
    got, bad, _ = parse_response(_envelope(fenced), cards)
    assert len(got) == 1
    assert bad == []


def test_an_error_envelope_is_reported() -> None:
    with pytest.raises(MalformedJsonError, match="claude reported an error"):
        parse_response(_envelope("rate limited", is_error=True), _cards())


def test_a_non_envelope_is_reported() -> None:
    with pytest.raises(MalformedJsonError, match="did not return a JSON envelope"):
        parse_response("[]", _cards())


def test_a_reply_that_is_not_an_array_is_reported() -> None:
    with pytest.raises(MalformedJsonError, match="did not return a JSON array"):
        parse_response(_envelope({"name": "x"}), _cards())


def test_a_card_that_was_never_asked_about_is_rejected() -> None:
    """A model naming a card outside the batch has invented one."""
    got, bad, _ = parse_response(_envelope([_reply("Black Lotus")]), _cards())
    assert got == []
    assert any("was not asked about" in b for b in bad)


def test_one_bad_proposal_does_not_lose_the_rest() -> None:
    """The same lesson as a bulk import: one odd card must not cost the others."""
    cards = _cards()
    body = [
        _reply(cards[0].name),
        _reply(cards[1].name, abilities=[{"kind": "teleport"}]),
        _reply(cards[2].name),
    ]
    got, bad, attempted = parse_response(_envelope(body), cards)
    assert [p.name for p in got] == [cards[0].name, cards[2].name]
    assert len(bad) == 1
    assert attempted == {cards[0].name, cards[1].name, cards[2].name}


def test_an_unknown_confidence_is_rejected() -> None:
    cards = _cards()
    body = [_reply(cards[0].name, confidence="certain")]
    _, bad, _ = parse_response(_envelope(body), cards)
    assert any("unknown confidence" in b for b in bad)


def test_a_proposal_that_is_not_an_object_is_rejected() -> None:
    _, bad, _ = parse_response(_envelope(["just a string"]), _cards())
    assert any("not an object" in b for b in bad)


def test_a_missing_confidence_defaults_to_low() -> None:
    """Silence about certainty is not a claim of certainty."""
    cards = _cards()
    body: list[object] = [{"name": cards[0].name, "abilities": []}]
    got, bad, _ = parse_response(_envelope(body), cards)
    assert bad == []
    assert got[0].confidence is Confidence.LOW


# --- omissions -------------------------------------------------------------


def test_a_card_never_mentioned_is_reported() -> None:
    cards = _cards()
    got, _, attempted = parse_response(_envelope([_reply(cards[0].name)]), cards)
    missing = omissions(cards, got, attempted)
    assert len(missing) == len(cards) - 1
    assert all("no proposal returned" in m for m in missing)


def test_a_rejected_card_is_not_also_reported_as_missing() -> None:
    """Counting it twice made 22 problems look like 44 and hid that none were absent."""
    cards = _cards()[:2]
    body = [_reply(cards[0].name), _reply(cards[1].name, abilities=[{"kind": "nope"}])]
    got, bad, attempted = parse_response(_envelope(body), cards)
    assert len(bad) == 1
    assert omissions(cards, got, attempted) == []


def test_without_the_attempted_set_everything_unanswered_is_missing() -> None:
    cards = _cards()[:2]
    assert len(omissions(cards, [])) == 2
