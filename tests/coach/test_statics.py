"""Static abilities: what combat applies, and what it admits it cannot."""

from __future__ import annotations

from helpers import ME, facts
from helpers_coach import Book, game, land
from mtgcoach.coach.report import TurnReport, advise
from mtgcoach.core.abilities import StaticModifier, StaticRestriction
from mtgcoach.core.steps import Step
from mtgcoach.core.targets import ANY_CREATURE, SELF
from mtgcoach.core.vocabulary import Restriction

FOREST, FOREST_RULES = land("Forest", "{G}")
BEAR = facts("Grizzly Bears", "{1}{G}", power=2, toughness=2, creature=True)
#: Vampire Interloper: "can't block" is a static ability about *itself*, which
#: is the one shape the engine can act on without tracking attachments.
INTERLOPER = facts("Vampire Interloper", "{1}{B}", power=2, toughness=1, creature=True)
CANT_BLOCK = StaticRestriction(Restriction.CANT_BLOCK, SELF)
CANT_ATTACK = StaticRestriction(Restriction.CANT_ATTACK, SELF)
#: Goblin Oriflamme: an anthem. The engine has no "affects other creatures".
ORIFLAMME = facts("Goblin Oriflamme", "{2}{R}")
ANTHEM = StaticModifier(1, 0, ANY_CREATURE)
#: Pacifism: about the creature it is attached to, and nothing tracks that.
PACIFISM = facts("Pacifism", "{1}{W}")
ENCHANTED_CANT_ATTACK = StaticRestriction(Restriction.CANT_ATTACK, ANY_CREATURE)

BOOK = Book(
    cards={
        "Forest": FOREST,
        "Bear": BEAR,
        "Interloper": INTERLOPER,
        "Oriflamme": ORIFLAMME,
        "Pacifism": PACIFISM,
    },
    rules={
        "Forest": FOREST_RULES,
        "Bear": (),
        "Interloper": (CANT_BLOCK,),
        "Oriflamme": (ANTHEM,),
        "Pacifism": (ENCHANTED_CANT_ATTACK,),
    },
)


def _combat(battlefield: tuple[str, ...] = (), theirs: tuple[str, ...] = ()) -> TurnReport:
    """A board at the moment attackers are declared."""
    state = game(battlefield=battlefield, theirs=theirs, step=Step.DECLARE_ATTACKERS)
    return advise(state, ME, BOOK)


def test_a_creature_that_cannot_block_is_not_counted_as_one() -> None:
    """Vampire Interloper across the table does not make your attack worse."""
    report = _combat(battlefield=("Bear",), theirs=("Interloper",))
    best = report.attacks.plans[0]
    assert best.names == ("Grizzly Bears",)
    assert best.outcome.damage_to_defender == 2, "nothing legally blocks it"


def test_a_creature_that_can_block_still_does() -> None:
    report = _combat(battlefield=("Bear",), theirs=("Bear",))
    assert report.attacks.plans[0].names == (), "attacking into an even trade is not best"


def test_a_creature_that_cannot_attack_is_not_offered() -> None:
    book = Book(cards=BOOK.cards, rules={**BOOK.rules, "Interloper": (CANT_ATTACK,)})
    report = advise(game(battlefield=("Interloper",), step=Step.DECLARE_ATTACKERS), ME, book)
    assert all(plan.names == () for plan in report.attacks.plans)


def test_an_anthem_the_engine_cannot_apply_is_disclosed() -> None:
    """A confident wrong number is worse than a hedged one."""
    report = _combat(battlefield=("Bear", "Oriflamme"))
    assert any("power/toughness" in caveat for caveat in report.attacks.caveats)
    assert any("Goblin Oriflamme" in caveat for caveat in report.attacks.caveats)
    assert report.attacks.plans, "the plans are still the best available"


def test_an_aura_on_the_other_side_is_disclosed_too() -> None:
    report = _combat(battlefield=("Bear",), theirs=("Pacifism",))
    assert any("Pacifism" in caveat for caveat in report.attacks.caveats)


def test_a_plain_board_has_nothing_to_disclose() -> None:
    assert _combat(battlefield=("Bear",), theirs=("Bear",)).attacks.caveats == ()


def test_a_caveat_survives_a_refusal() -> None:
    """The numbers being unavailable does not make the board less complicated."""
    star = facts("Consuming Aberration", "{3}{U}{B}", creature=True)
    book = Book(
        cards={**BOOK.cards, "Star": star},
        rules={**BOOK.rules, "Star": ()},
    )
    report = advise(game(battlefield=("Star", "Oriflamme"), step=Step.DECLARE_ATTACKERS), ME, book)
    assert report.attacks.unavailable
    assert report.attacks.caveats
