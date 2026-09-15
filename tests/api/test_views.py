"""The JSON on the wire, which is the contract the app is written against."""

from __future__ import annotations

import json
from dataclasses import replace

from helpers import ME, YOU, deck, facts
from helpers_coach import Book, game, land
from mtgcoach.api import boardview, views
from mtgcoach.coach.report import advise
from mtgcoach.core.abilities import Trigger, TriggeredAbility
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId
from mtgcoach.core.stack import StackObject
from mtgcoach.core.state import GameState, start_game
from mtgcoach.core.steps import Step
from mtgcoach.core.vocabulary import TriggerEvent
from wire import at, flag, number, rows, text, words

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
BOOK = Book(
    cards={"Forest": FOREST, "Bear": BEAR},
    rules={"Forest": FOREST_RULES, "Bear": ()},
)


def test_everything_it_produces_is_json() -> None:
    """The one property that matters: it has to survive `json.dumps`."""
    state = game(hand=("Bear", "Forest"), battlefield=("Forest", "Forest"))
    payload = {
        "state": boardview.state(state, BOOK, str(ME)),
        "advice": views.report(advise(state, ME, BOOK)),
    }
    assert json.loads(json.dumps(payload)) == json.loads(json.dumps(payload))


def test_a_library_is_a_count_and_never_a_list() -> None:
    """A tracker that shows you the top of a deck is a cheating tool."""
    state = start_game({ME: deck("m"), YOU: deck("y")}, ME)
    rendered = boardview.state(state, BOOK, str(ME))
    for name in ("me", "you"):
        assert isinstance(at(rendered, "players", name, "library"), int)


def _waiting(oracle: str) -> GameState:
    """A board with one spell of ``oracle`` on the shared stack, cast by ME."""
    card = CardInstance(InstanceId(f"{oracle}-cast"), OracleId(oracle))
    return replace(game(), stack=(StackObject(card, ME),))


def test_a_spell_on_the_stack_says_whose_it_is_and_where_it_is_going() -> None:
    """Both of the things a shared, ordered stack has to tell a client.

    Its controller (CR 405.4), because a zone two players share has to say
    whose each object is -- one filed under each player used to answer that by
    where it sat, and could not answer which resolves first.

    And its destination, which only this side knows: ``core`` cannot read a
    type line, ``resolve_spell`` has to carry the answer, and the app used to
    remember it from the hand advice -- holding a fact about a card after the
    card had left the zone it read it from.
    """
    (spell,) = rows(boardview.state(_waiting("Bear"), BOOK, str(ME)), "stack")
    assert text(spell, "name") == "Grizzly Bears"
    assert text(spell, "controller") == "me"
    assert text(spell, "resolves_to") == "battlefield"


def test_a_spell_the_coach_cannot_name_gets_no_destination_guessed_for_it() -> None:
    """Null, not a zone. The one answer that cannot be wrong.

    Nothing about an unknown card says whether it stays on the battlefield, and
    a guess is how an Opt ends up among the lands for the rest of a game.
    ``api.guard`` refuses that resolution for the same reason, so a client
    offering the button would only be offering a refusal.
    """
    (spell,) = rows(boardview.state(_waiting("Mystery"), BOOK, str(ME)), "stack")
    assert spell["resolves_to"] is None
    assert text(spell, "name") == "Mystery"


def test_the_board_says_who_may_act_and_who_has_passed() -> None:
    """The fields the app had no way to ask for (CR 117.1, CR 117.4).

    Both devices need all three: one to know it is waiting, the other to know
    it is being waited for, and either to know when nobody may act at all.
    """
    rendered = boardview.state(game(), BOOK, str(ME))
    assert text(rendered, "priority") == "me"
    assert words(rendered, "passed") == []
    assert words(rendered, "yet_to_pass") == ["me", "you"]


def test_nobody_holding_priority_is_null_rather_than_missing() -> None:
    """CR 502.4: the untap step hands it to nobody, which is an answer."""
    rendered = boardview.state(game(step=Step.UNTAP), BOOK, str(ME))
    assert rendered["priority"] is None
    assert words(rendered, "yet_to_pass") == []


def test_a_card_carries_both_of_its_identities_and_its_name() -> None:
    state = game(hand=("Bear",))
    (card,) = rows(boardview.state(state, BOOK, str(ME)), "players", "me", "hand")
    assert text(card, "oracle_id") == "Bear"
    assert text(card, "name") == "Grizzly Bears"
    assert text(card, "instance_id").startswith("Bear")


def test_a_permanent_carries_the_two_states_a_tracker_has_to_show() -> None:
    state = game(battlefield=("Forest",))
    (permanent,) = rows(boardview.state(state, BOOK, str(ME)), "players", "me", "battlefield")
    assert flag(permanent, "tapped") is False
    assert flag(permanent, "summoning_sick") is False


def test_an_unnamed_card_falls_back_to_its_identifier() -> None:
    """Better than a blank, which a player would read as a bug."""
    state = game(hand=("Mystery",))
    (card,) = rows(boardview.state(state, BOOK, str(ME)), "players", "me", "hand")
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
