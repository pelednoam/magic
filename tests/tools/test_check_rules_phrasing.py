"""The check that keeps the paraphrase map matching the real document.

`phrasing` searches for the wording the Comprehensive Rules use. Wizards
revise those with every set, so a target they reword stops matching anything
and the only symptom is a rules answer quietly going back to "the rules I was
given don't cover this". The unit tests use a hand-written excerpt, where the
phrases are right by construction; this reads the installed document instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import check_rules_phrasing as gate
from mtgcoach.rules.terms import TARGETS

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

#: A document containing every phrase, in sentences close to the real ones.
GOOD = """
302.6. A creature can't attack unless it has been under its controller's
control continuously since their most recent turn began. This rule is
informally called the "summoning sickness" rule.

110.2. A permanent's controller is, by default, the player under whose control
it entered the battlefield.

119.1. Each player begins the game with a starting life total of 20.

119.6. If a player has 0 or less life, that player loses the game as a
state-based action.

509.1a. The defending player chooses which creatures they control, if any,
will block. The chosen creatures must be untapped.

510.1b. An unblocked creature assigns its combat damage to the player or
planeswalker it's attacking.

121.4. A player who attempts to draw a card from a library with no cards in it
loses the game the next time a player would receive priority.

115.2. Only permanents are legal targets for spells and abilities.

601.2c The player announces their choice of an appropriate object or player for
each target the spell requires.

700.4. The term dies means "is put into a graveyard from the battlefield."

704.5g. If a creature has toughness greater than 0 and the total damage marked
on it is greater than or equal to its toughness, that creature has been dealt
lethal damage and is destroyed.
"""


def test_a_document_with_every_phrase_in_it_passes() -> None:
    assert gate.missing(GOOD) == []


def test_the_comparison_ignores_case() -> None:
    """The document capitalises a phrase at the start of a sentence."""
    assert gate.missing(GOOD.upper()) == []


def test_a_reworded_target_is_reported() -> None:
    """The failure this exists for.

    "Summoning sickness" is informal, so it is exactly the kind of sentence a
    revision drops -- and the phrase is what makes 302.6 findable at all.
    """
    reworded = GOOD.replace("summoning sickness", "creature-not-ready")
    assert gate.missing(reworded) == ["summoning sickness"]


def test_every_target_is_reported_when_the_document_is_something_else() -> None:
    assert gate.missing("Published by Wizards of the Coast LLC.") == sorted(TARGETS)


def test_the_phrases_come_from_the_map_rather_than_a_copy_of_it() -> None:
    """A copy is the same failure one level up.

    Somebody adds an entry to `phrasing` and not here, and the check passes
    having looked for the old ones.
    """
    assert gate.missing("", TARGETS) == sorted(TARGETS)


def test_it_skips_loudly_when_the_rules_are_not_installed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """They are not vendored, so a fresh checkout has none.

    Printing rather than passing silently, because a green run on such a
    machine says nothing about the phrases.
    """
    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    assert gate.main() == 0
    assert "SKIPPED" in capsys.readouterr().out


def test_it_passes_on_a_document_that_has_them(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _install(tmp_path, GOOD)
    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    assert gate.main() == 0


def test_it_fails_and_names_the_phrase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _install(tmp_path, GOOD.replace("life total", "hit points"))
    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    assert gate.main() == 1
    printed = capsys.readouterr().out
    assert "life total" in printed
    assert "Update the map" in printed


def test_a_document_that_cannot_be_read_is_a_failure_not_a_crash(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A directory where the file should be, or a permission problem.

    The gate wants an exit code and a sentence, not a traceback.
    """
    _install(tmp_path, GOOD)

    def refuse(*_args: object, **_kwargs: object) -> str:
        msg = "permission denied"
        raise OSError(msg)

    monkeypatch.setattr(gate, "DEFAULT_DATA", tmp_path)
    monkeypatch.setattr("pathlib.Path.read_text", refuse)
    assert gate.main() == 1
    assert "could not read" in capsys.readouterr().out


def _install(data_root: Path, document: str) -> None:
    """Write a rules document where the checker will look for it."""
    where = data_root / "rules"
    where.mkdir(parents=True, exist_ok=True)
    (where / "comprehensive.txt").write_text(document, encoding="utf-8")
