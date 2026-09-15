"""The shipped fixture's Aura and Equipment data, asked of the real cards.

Every other test in this area builds its own representation of a card, and that
is why the bug this file exists for shipped. ``tests/coach/test_statics.py``
hand-built Pacifism as a restriction on ANY_CREATURE, which takes the "cannot
apply this, disclose it" branch and passes. The *shipped* Pacifism said
``self`` -- meaning, to the engine, Pacifism itself -- so it took the "can
apply this" branch instead, was exempted from the caveat, and combat advice
ignored the Pacifism on the table while saying nothing about doing so.

So these read `data/sets/FDN/effects.json` and assert on what is actually in
it. A test that builds its own card cannot catch a fixture that is wrong.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Final

from mtgcoach.core.targets import TargetKind

#: The sealed fixture the engine reads at runtime.
FIXTURE: Final = Path(__file__).resolve().parents[2] / "data" / "sets" / "FDN" / "effects.json"

#: Every card in the Beginner Box whose static abilities are about something it
#: is attached to rather than about itself.
ATTACHING: Final = ("Pacifism", "Starlight Snare", "Pirate's Cutlass")

#: The kinds of ability whose subject is the attached permanent. A *trigger's*
#: subject is not: "when Pirate's Cutlass enters" is about the Cutlass.
ABOUT_THE_ATTACHED: Final = ("static_restriction", "static_modifier")


def shipped() -> list[dict[str, object]]:
    """The fixture's card entries."""
    loaded = json.loads(FIXTURE.read_text(encoding="utf-8"))
    cards = loaded["cards"]
    assert isinstance(cards, list)
    return cards


def entry(name: str) -> dict[str, object]:
    """One card's shipped entry."""
    found = next((card for card in shipped() if card["name"] == name), None)
    assert found is not None, f"{name} is not in the shipped fixture"
    return found


def statics(name: str) -> list[dict[str, object]]:
    """A card's static abilities, as shipped."""
    abilities = entry(name).get("abilities") or []
    assert isinstance(abilities, list)
    return [one for one in abilities if one.get("kind") in ABOUT_THE_ATTACHED]


def test_the_fixture_is_where_it_is_thought_to_be() -> None:
    """A moved fixture would make everything below vacuously true."""
    assert FIXTURE.is_file()
    assert len(shipped()) > 1


def test_no_static_ability_claims_self_for_what_it_is_attached_to() -> None:
    """The bug, as a property of the whole fixture.

    ``self`` is the permanent the ability is printed on. An Aura's "enchanted
    creature" and an Equipment's "equipped creature" are a different permanent,
    and saying ``self`` for them makes the engine apply the restriction to the
    Aura -- which can neither attack nor block, so the restriction does nothing
    and the disclosure that it did nothing is skipped.
    """
    for name in ATTACHING:
        for ability in statics(name):
            affects = ability.get("affects") or {}
            assert isinstance(affects, dict)
            kinds = affects.get("kinds")
            assert kinds == [TargetKind.ENCHANTED.value], f"{name}: {ability['kind']} says {kinds}"


def test_pacifism_restricts_what_it_enchants() -> None:
    """Both halves of its one printed sentence, on the right permanent."""
    restrictions = {one["restriction"] for one in statics("Pacifism")}
    assert restrictions == {"cant_attack", "cant_block"}


def test_an_equipments_enters_trigger_is_still_about_itself() -> None:
    """The distinction the fix must not flatten.

    "When Pirate's Cutlass enters" is about the Cutlass. Only "equipped
    creature gets +2/+1" is about what it is attached to -- so a change that
    rewrote every ``self`` in the card would be wrong in the other direction.
    """
    abilities = entry("Pirate's Cutlass").get("abilities") or []
    assert isinstance(abilities, list)
    triggers = [one for one in abilities if one.get("kind") == "triggered"]
    assert triggers
    for trigger in triggers:
        subject = trigger.get("subject") or {}
        assert isinstance(subject, dict)
        assert subject.get("kinds") == [TargetKind.SELF.value]


def test_the_notes_say_which_is_which() -> None:
    """The note is what a reviewer reads before sealing.

    The old one stated the wrong convention as a rule, which is how the data
    came to be wrong and stayed wrong: a reviewer checking the entry against
    its note would have found them in agreement.
    """
    for name in ATTACHING:
        note = entry(name).get("notes")
        assert isinstance(note, str)
        assert "enchanted" in note
        assert "self" in note
