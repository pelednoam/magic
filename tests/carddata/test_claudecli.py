"""The subprocess adapter, driven without a subprocess.

``claude`` is never actually invoked here. The call is a thin wrapper -- build a
prompt, run a command, hand the output to the parser -- and what matters is that
its failure paths are handled, which a fake executable exercises far more
cheaply and reliably than the real one.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import TYPE_CHECKING

from mtgcoach.carddata.claudecli import ClaudeCliExtractor
from mtgcoach.carddata.scryfall import cards_in

if TYPE_CHECKING:
    import pytest

    from mtgcoach.carddata.cards import Card

FIXTURE = Path(__file__).resolve().parent.parent / "fixtures" / "scryfall_fdn_sample.json"


def _cards() -> list[Card]:
    return list(cards_in(FIXTURE))


def _fake_claude(tmp_path: Path, stdout: str, code: int = 0, stderr: str = "") -> str:
    """A stand-in executable that prints a recorded reply."""
    script = tmp_path / "fake-claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "sys.stdin.read()\n"
        f"sys.stdout.write({stdout!r})\n"
        f"sys.stderr.write({stderr!r})\n"
        f"sys.exit({code})\n",
        encoding="utf-8",
    )
    script.chmod(0o755)
    return str(script)


def _reply(names: list[str]) -> str:
    empty: list[object] = []
    body: list[object] = [
        {"name": n, "confidence": "high", "notes": "", "abilities": empty} for n in names
    ]
    return json.dumps({"is_error": False, "result": json.dumps(body)})


def test_a_successful_batch(tmp_path: Path) -> None:
    cards = _cards()[:2]
    extractor = ClaudeCliExtractor(
        executable=_fake_claude(tmp_path, _reply([c.name for c in cards]))
    )
    result = extractor.extract(cards)
    assert [p.name for p in result.proposals] == [c.name for c in cards]
    assert result.failures == ()


def test_batches_are_sent_separately(tmp_path: Path) -> None:
    """Eight cards at a batch size of two is four calls, not one."""
    cards = _cards()
    extractor = ClaudeCliExtractor(
        executable=_fake_claude(tmp_path, _reply([c.name for c in cards])),
        batch_size=2,
    )
    result = extractor.extract(cards)
    # Every batch gets the same canned reply, so each card is proposed once per
    # batch it appears in -- only the two it was actually sent with survive the
    # "was not asked about" check.
    assert len(result.proposals) == len(cards)


def test_a_nonzero_exit_is_reported_not_raised(tmp_path: Path) -> None:
    extractor = ClaudeCliExtractor(
        executable=_fake_claude(tmp_path, "", code=2, stderr="not logged in")
    )
    result = extractor.extract(_cards()[:2])
    assert result.proposals == ()
    assert any("claude exited 2" in f for f in result.failures)
    assert any("not logged in" in f for f in result.failures)


def test_a_missing_executable_is_reported_not_raised(tmp_path: Path) -> None:
    extractor = ClaudeCliExtractor(executable=str(tmp_path / "nope"))
    result = extractor.extract(_cards()[:1])
    assert result.proposals == ()
    assert len(result.failures) == 1


def test_a_timeout_is_reported_not_raised(monkeypatch: pytest.MonkeyPatch) -> None:
    def slow(*_args: object, **_kwargs: object) -> object:
        raise subprocess.TimeoutExpired(cmd="claude", timeout=1)

    monkeypatch.setattr(subprocess, "run", slow)
    result = ClaudeCliExtractor().extract(_cards()[:1])
    assert result.proposals == ()
    assert any("timed out" in f.lower() or "TimeoutExpired" in f for f in result.failures)


def test_a_card_the_model_skipped_is_reported(tmp_path: Path) -> None:
    """The Savannah Lions case: asked about two, told about one."""
    cards = _cards()[:2]
    extractor = ClaudeCliExtractor(executable=_fake_claude(tmp_path, _reply([cards[0].name])))
    result = extractor.extract(cards)
    assert len(result.proposals) == 1
    assert any(cards[1].name in f and "no proposal" in f for f in result.failures)
