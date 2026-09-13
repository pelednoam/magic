"""Type line parsing."""

from __future__ import annotations

import pytest

from mtgcoach.carddata.typeline import TYPE_SEPARATOR, parse_type_line


def test_full_type_line() -> None:
    line = parse_type_line(f"Legendary Creature {TYPE_SEPARATOR} Elf Warlock")
    assert line.supertypes == {"Legendary"}
    assert line.types == {"Creature"}
    assert line.subtypes == {"Elf", "Warlock"}


def test_a_line_with_no_dash_has_no_subtypes() -> None:
    line = parse_type_line("Instant")
    assert line.types == {"Instant"}
    assert line.subtypes == frozenset()
    assert line.supertypes == frozenset()


def test_an_empty_line_parses_to_nothing() -> None:
    line = parse_type_line("")
    assert line.types == frozenset()
    assert not line.is_permanent


def test_basic_land() -> None:
    line = parse_type_line(f"Basic Land {TYPE_SEPARATOR} Forest")
    assert line.supertypes == {"Basic"}
    assert line.is_land
    assert line.is_permanent


#: Checked exhaustively, so a predicate that is unexpectedly true also fails.
PREDICATES = ("is_land", "is_creature", "is_permanent", "is_instant_speed")


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Creature — Turtle", {"is_creature", "is_permanent"}),
        ("Land", {"is_land", "is_permanent"}),
        ("Instant", {"is_instant_speed"}),
        ("Sorcery", set[str]()),
        ("Artifact — Equipment", {"is_permanent"}),
        ("Artifact Creature — Golem", {"is_creature", "is_permanent"}),
        ("Land Creature — Dryad", {"is_land", "is_creature", "is_permanent"}),
    ],
)
def test_predicates(text: str, expected: set[str]) -> None:
    line = parse_type_line(text.replace("—", TYPE_SEPARATOR))
    assert {name for name in PREDICATES if getattr(line, name)} == expected
