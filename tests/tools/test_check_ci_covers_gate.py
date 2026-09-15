"""CI must run the gate the README promises.

The two definitions drifted: the workflow omitted the CLI-flag check, both
rules checks, the TypeScript typecheck and the whole mobile test suite, while
the README called it the full gate. Nothing noticed, because nothing was
looking.

These tests are about the looking. The last one is the important one -- it
reconstructs the workflow as it was when the drift was found and asserts the
checker reports exactly the five checks that were missing, so a checker that
had quietly stopped working would fail here rather than pass everything.
"""

from __future__ import annotations

from pathlib import Path

from check_ci_covers_gate import (
    EXEMPT,
    GATE,
    WORKFLOW,
    commands,
    main,
    missing,
    normalised,
    report,
)

#: The five checks CI was not running when the ensemble review found R10.
DRIFTED = ("check_cli_flags", "check_rules_phrasing", "check_retrieval", "tsc --noEmit", "vitest")

ROOT = Path(__file__).resolve().parents[2]


def _without(workflow: str, dropped: tuple[str, ...]) -> str:
    """The workflow with some checks taken back out of it."""
    return "\n".join(
        line for line in workflow.splitlines() if not any(one in line for one in dropped)
    )


def test_the_repositorys_own_ci_runs_its_own_gate() -> None:
    """The check, applied to this repository. The point of the whole file."""
    assert main(["--root", str(ROOT)]) == 0


def test_the_drift_that_was_actually_there_is_caught() -> None:
    """Guard on the guard, against the real historical case.

    A checker that matched nothing would pass every test above. This rebuilds
    the workflow as it was and asserts all five omissions are named.
    """
    gate = (ROOT / GATE).read_text(encoding="utf-8")
    found = missing(gate, _without((ROOT / WORKFLOW).read_text(encoding="utf-8"), DRIFTED))
    assert len(found) == len(DRIFTED)
    for one in DRIFTED:
        assert any(one in command for command in found), one


def test_a_workflow_doing_more_than_the_gate_is_fine() -> None:
    """CI fetches the Comprehensive Rules; a developer installs them once.

    The comparison is one-directional on purpose: a workflow forbidden from
    adding a check would be a worse workflow.
    """
    assert missing('echo "== one" && uv run true', "run: uv run true\nrun: uv run extra") == []


def test_the_commands_are_read_off_the_gate() -> None:
    """Matched on the command, not the step name: a name is prose."""
    assert commands('echo "== mypy" && uv run mypy\n') == ["uv run mypy"]


def test_a_missing_command_is_reported_with_what_to_do() -> None:
    absent = missing('echo "== mypy" && uv run mypy\n', "nothing here")
    assert absent == ["uv run mypy"]
    assert report(absent) == 1


def test_nothing_missing_is_silent() -> None:
    assert report([]) == 0


def test_the_noise_a_workflow_legitimately_adds_is_ignored() -> None:
    """Noise a workflow adds is not the check being different.

    CI annotates the diff and runs the app's checks from a working-directory
    rather than a subshell `cd`. A literal comparison would call both a
    mismatch, and be useless.
    """
    assert normalised("uv run ruff check --output-format=github .") == "uv run ruff check ."
    assert normalised("(cd apps/mobile && npx --no-install tsc --noEmit)") == "npx tsc --noEmit"


def test_the_exempt_list_explains_itself() -> None:
    """An exemption list with no reasons is how this becomes decorative."""
    assert EXEMPT
    for command, why in EXEMPT:
        assert command
        assert why


def test_an_exempt_command_is_not_reported() -> None:
    """`npm install` is advice to a developer, not a check CI runs.

    The gate prints it when `node_modules` is absent. A workflow that ran it
    would be resolving its own dependency versions, which is what `npm ci`
    exists not to do.
    """
    gate = 'echo "== app" && npm install\n'
    assert missing(gate, "nothing at all") == []
