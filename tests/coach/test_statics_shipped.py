"""What combat discloses about the *real* Pacifism, not a hand-built one.

``test_statics`` builds its own representations, which is right for testing the
logic and is exactly why the fixture bug survived: its Pacifism restricted
ANY_CREATURE, which takes the disclose branch, while the shipped one said
``self`` and took the apply branch. Both tests passed. One of them was about a
card that does not exist.

The review's acceptance criterion for that finding was "the real shipped
Pacifism entry produces the intended behavior or an explicit unsupported
result". This is that criterion.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Final

import pytest

from mtgcoach.api.cards import Catalogue, build
from mtgcoach.carddata.paths import effects_path
from mtgcoach.carddata.store import CardStore
from mtgcoach.coach.statics import cannot_attack, cannot_block, caveats
from mtgcoach.core.abilities import StaticRestriction
from mtgcoach.core.cards import CardInstance
from mtgcoach.core.ids import InstanceId, OracleId, SetCode
from mtgcoach.core.permanents import Permanent
from mtgcoach.core.targets import TargetKind

if TYPE_CHECKING:
    from collections.abc import Sequence

#: The imported card database, which is a local install and not in the tree.
DB: Final = Path("data/cards.sqlite3")
DATA: Final = Path("data")
FDN: Final = SetCode("FDN")

#: A card whose restriction really is about itself, as a control: whatever the
#: Aura cards do, this one must still be *applied* rather than disclosed.
ITSELF: Final = "Vampire Interloper"


@pytest.fixture(scope="module")
def catalogue() -> Catalogue:
    """The real Foundations catalogue, or a skip."""
    if not DB.is_file():
        pytest.skip(f"{DB} is not imported; run `mtgcoach sets add FDN`")
    with CardStore.open(str(DB)) as store:
        cards = store.cards_in_set(FDN)
    if not cards:
        pytest.skip("no FDN cards imported")
    return build(cards, effects_path(DATA, FDN))


def named(catalogue: Catalogue, name: str) -> OracleId:
    """One card's oracle id, by the name printed on it."""
    found = next((oid for oid, card in catalogue.cards.items() if card.name == name), None)
    assert found is not None, f"{name} is not in the imported set"
    return OracleId(found)


def board(catalogue: Catalogue, *names: str) -> Sequence[Permanent]:
    """A battlefield holding one of each named card."""
    return [
        Permanent(CardInstance(InstanceId(f"c{n}"), named(catalogue, name)))
        for n, name in enumerate(names)
    ]


def test_the_real_pacifism_is_disclosed(catalogue: Catalogue) -> None:
    """Combat says out loud that it is not accounting for it.

    Not silence, which is what shipped: the fixture said the restriction was
    about Pacifism itself, so the engine believed it had applied it.
    """
    found = caveats([board(catalogue, "Pacifism")], catalogue)
    assert len(found) == 1
    assert found[0].startswith("Pacifism:")
    assert "attached" in found[0]


def test_the_real_pacifism_does_not_restrict_itself(catalogue: Catalogue) -> None:
    """Because it is an enchantment, and enchantments do not attack.

    The engine used to answer True to both of these, which is true and useless
    -- and it is what made the card look handled.
    """
    abilities = catalogue.abilities(named(catalogue, "Pacifism"))
    assert not cannot_attack(abilities)
    assert not cannot_block(abilities)


def test_a_creature_whose_restriction_really_is_its_own_is_applied(
    catalogue: Catalogue,
) -> None:
    """The control. Vampire Interloper "can't block" is about the Interloper.

    Without this, making Pacifism disclose could have been achieved by making
    *everything* disclose, which would be a worse engine that passed the test
    above.
    """
    abilities = catalogue.abilities(named(catalogue, ITSELF))
    assert cannot_block(abilities)
    assert caveats([board(catalogue, ITSELF)], catalogue) == ()


def test_every_card_restricting_what_it_is_attached_to_is_disclosed(
    catalogue: Catalogue,
) -> None:
    """Whichever cards those turn out to be.

    Found by asking the catalogue rather than from a list in this file, so a
    card added by a later set import is covered on the day it is imported.
    Hard-coding the names is the mistake that let the first one through: the
    only test of Pacifism was of a Pacifism somebody had typed out.
    """
    attaching = sorted(
        card.name
        for oid, card in catalogue.cards.items()
        if any(
            isinstance(ability, StaticRestriction) and TargetKind.ENCHANTED in ability.affects.kinds
            for ability in catalogue.abilities(OracleId(oid))
        )
    )
    assert attaching, "no card in the box restricts what it is attached to"
    for name in attaching:
        found = caveats([board(catalogue, name)], catalogue)
        assert found, f"{name} restricts an attached permanent and says nothing about it"
