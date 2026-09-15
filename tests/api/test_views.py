"""The JSON on the wire, which is the contract the app is written against."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from helpers import ME, YOU, deck, facts
from helpers_coach import Book, game, land
from mtgcoach.api import boardview, views
from mtgcoach.coach.report import advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.state import start_game
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent
from wire import at, flag, number, rows, text, words

if TYPE_CHECKING:
    from mtgcoach.core.ids import OracleId

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR},
    rules={"Forest": FOREST_RULES, "Bear": ()},
)


def _names(oracle_id: OracleId) -> str:
    card = BOOK.facts(oracle_id)
    return card.name if card is not None else str(oracle_id)


def test_everything_it_produces_is_json() -> None:
    """The one property that matters: it has to survive `json.dumps`."""
    state = game(hand=("Bear", "Forest"), battlefield=("Forest", "Forest"))
    payload = {
        "state": boardview.state(state, _names),
        "advice": views.report(advise(state, ME, BOOK)),
    }
    assert json.loads(json.dumps(payload)) == json.loads(json.dumps(payload))


def test_a_library_is_a_count_and_never_a_list() -> None:
    """A tracker that shows you the top of a deck is a cheating tool."""
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    rendered = boardview.state(state, _names)
    for name in ("me", "you"):
        assert isinstance(at(rendered, "players", name, "library"), int)


def test_a_card_carries_both_of_its_identities_and_its_name() -> None:
    state = game(hand=("Bear",))
    (card,) = rows(boardview.state(state, _names), "players", "me", "hand")
    assert text(card, "oracle_id") == "Bear"
    assert text(card, "name") == "Grizzly Bears"
    assert text(card, "instance_id").startswith("Bear")


def test_a_permanent_carries_the_two_states_a_tracker_has_to_show() -> None:
    state = game(battlefield=("Forest",))
    (permanent,) = rows(boardview.state(state, _names), "players", "me", "battlefield")
    assert flag(permanent, "tapped") is False
    assert flag(permanent, "summoning_sick") is False


def test_an_unnamed_card_falls_back_to_its_identifier() -> None:
    """Better than a blank, which a player would read as a bug."""
    state = game(hand=("Mystery",))
    (card,) = rows(boardview.state(state, _names), "players", "me", "hand")
    assert text(card, "name") == "Mystery"


def test_the_report_carries_the_reasons_not_just_the_verdict() -> None:
    state = game(hand=("Bear",), battlefield=("Forest",))
    rendered = views.report(advise(state, ME, BOOK))
    (card,) = rows(rendered, "hand")
    assert flag(card, "playable") is False
    assert "you need 1 more untapped source" in words(card, "reasons")
    assert card["payment"] is None


def test_a_payment_says_what_to_tap_and_what_to_keep() -> None:
    state = game(hand=("Bear",), battlefield=("Forest", "Forest", "Forest"))
    (card,) = rows(views.report(advise(state, ME, BOOK)), "hand")
    assert len(words(card, "payment", "tap")) == 2
    assert len(words(card, "payment", "keep")) == 1


def test_an_attack_plan_shows_the_maths() -> None:
    state = game(battlefield=("Bear",), step=Step.DECLARE_ATTACKERS)
    best = rows(views.report(advise(state, ME, BOOK)), "attacks", "plans")[0]
    assert words(best, "attackers") == ["Grizzly Bears"]
    assert number(best, "damage") == 2
    assert number(best, "defender_life_after") == 18
    assert flag(best, "lethal") is False
    assert words(best, "you_lose") == []


def test_an_unavailable_attack_section_carries_the_sentence() -> None:
    state = game(battlefield=("Bear",))
    rendered = views.report(advise(state, ME, BOOK))
    assert rows(rendered, "attacks", "plans") == []
    assert "declare attackers step" in text(rendered, "attacks", "unavailable")


def test_a_reminder_names_the_card_and_the_event() -> None:
    book = Book(
        cards={"Bell": facts("Bell", creature=True, power=1, toughness=1)},
        rules={"Bell": (TriggeredAbility(Trigger(TriggerEvent.BEGINNING_OF_UPKEEP), ()),)},
    )
    state = game(battlefield=("Bell",), step=Step.UPKEEP)
    (rendered,) = rows(views.report(advise(state, ME, book)), "reminders")
    assert text(rendered, "name") == "Bell"
    assert text(rendered, "event") == "beginning_of_upkeep"


def test_unmodelled_cards_are_named_on_the_wire() -> None:
    state = game(hand=("Mystery",))
    assert words(views.report(advise(state, ME, BOOK)), "unknown") == ["Mystery"]
