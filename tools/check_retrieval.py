"""Check that retrieval still finds the rule each question is about.

Everything else in the rules package is checkable against a hand-written
excerpt. Retrieval is not: it is a *ranking* over three and a half thousand
passages, and whether the right one comes back depends on how common every
word is in the whole document. A twenty-passage fixture cannot tell you that,
and it will happily agree with a change that ruins the real thing.

So this asks the installed Comprehensive Rules the questions a person at a
kitchen table would actually type, and checks an answering rule comes back in
the top eight. The questions and their acceptable references are in
``retrieval_questions.json`` beside this file.

Two rules about that list, both about honesty:

* a question marked ``gap`` is one retrieval does not answer yet. It does not
  fail the check -- writing it down is the point -- and when one starts passing
  the check says so, so the note gets removed rather than quietly outliving
  the problem.
* everything else must pass. A change that drops a question is a regression in
  the feature this project exists for, and the failure names the question, what
  was wanted and what came back.

Skipped, loudly, when the rules are not installed -- they are Wizards'
document, not vendored, and a machine without them cannot answer a rules
question anyway. The skip prints rather than passing silently.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Final, cast

from mtgcoach.rules.corpus import CorpusError, passages_in
from mtgcoach.rules.library import rules_path
from mtgcoach.rules.search import DEFAULT_LIMIT, RuleIndex

#: Where the server looks for the document by default.
DEFAULT_DATA: Final = Path("data")

#: The questions, beside this file so the list reads as data.
QUESTIONS: Final = Path(__file__).resolve().parent / "retrieval_questions.json"


def asked(path: Path) -> list[dict[str, object]]:
    """The question list.

    Takes the path rather than defaulting to ``QUESTIONS``: a default argument
    binds once at import, so a test replacing the module's ``QUESTIONS`` would
    have been silently ignored -- and was.

    Raises:
        ValueError: If the file is not the shape this expects.
    """
    loaded: object = json.loads(path.read_text(encoding="utf-8"))
    questions = (
        cast("dict[str, object]", loaded).get("questions") if isinstance(loaded, dict) else None
    )
    if not isinstance(questions, list) or not questions:
        msg = f"{path} has no question list in it"
        raise ValueError(msg)
    asking = cast("list[object]", questions)
    return [_checked(entry, index, path) for index, entry in enumerate(asking, 1)]


def _checked(entry: object, index: int, path: Path) -> dict[str, object]:
    """One question, or a refusal naming which one.

    Malformed entries used to be filtered out with ``isinstance(entry, dict)``
    and the rest checked as though nothing were missing. A bad edit or a JSON
    transform could therefore cost coverage in silence -- and an entry that was
    only ``{"gap": "..."}`` was reported as an allowed gap, which is a way of
    marking a question as known-broken without ever asking it.

    Raises:
        ValueError: If the entry is not a question.
    """
    if not isinstance(entry, dict):
        # ValueError, not TypeError: the caller catches one thing for "the
        # question file is wrong", and a bad JSON *value* is a content problem
        # rather than somebody passing the wrong argument.
        msg = f"{path} question {index} is {type(entry).__name__}, not an object"
        raise ValueError(msg)  # noqa: TRY004 - a bad file, not a bad call
    question = cast("dict[str, object]", entry)
    if not str(question.get("ask", "")).strip():
        msg = f"{path} question {index} has no 'ask'"
        raise ValueError(msg)
    wanted = question.get("any")
    if not isinstance(wanted, list) or not wanted:
        msg = f"{path} question {index} ({question['ask']!r}) has no 'any' references"
        raise ValueError(msg)
    return question


def verdicts(index: RuleIndex, questions: list[dict[str, object]]) -> list[tuple[str, str, str]]:
    """One ``(state, question, detail)`` per question.

    ``state`` is "ok", "miss", "gap" (a known miss, still missing) or "fixed"
    (a known miss that now passes).
    """
    report: list[tuple[str, str, str]] = []
    for entry in questions:
        ask = str(entry.get("ask", ""))
        wanted = [str(reference) for reference in _listed(entry.get("any"))]
        found = [passage.reference for passage in index.search(ask, DEFAULT_LIMIT)]
        hit = any(reference in found for reference in wanted)
        known = "gap" in entry
        if hit:
            report.append(("fixed" if known else "ok", ask, str(entry.get("gap", ""))))
        else:
            report.append(("gap" if known else "miss", ask, f"wanted {wanted}, got {found}"))
    return report


def _listed(value: object) -> list[object]:
    """A JSON array, or nothing.

    Nothing rather than a failure: a question whose ``any`` is mistyped counts
    as a miss and is reported with what came back, which is more use than a
    parse error naming a line number.
    """
    return cast("list[object]", value) if isinstance(value, list) else []


def main() -> int:
    """Ask the questions, or say why the check was skipped."""
    rules = rules_path(DEFAULT_DATA)
    if not rules.is_file():
        print(f"== retrieval         SKIPPED: {rules} is not installed")
        return 0
    try:
        questions = asked(QUESTIONS)
        document = rules.read_text(encoding="utf-8", errors="replace")
        with RuleIndex.build(passages_in(document)) as index:
            report = verdicts(index, questions)
    except (OSError, ValueError, CorpusError) as exc:
        print(f"could not run the retrieval check: {type(exc).__name__}: {exc}")
        return 1
    return said(report)


def said(report: list[tuple[str, str, str]]) -> int:
    """Print the outcome and decide the exit code.

    Public because the exit code is the whole contract with the gate, and a
    test that has to reach past an underscore to check it tends not to exist.
    """
    if not report:
        # A gate that asked nothing must not report a pass. "0/0 questions
        # answered" and exit 0 is indistinguishable from a green run, and the
        # ways to get here -- a filtered-away list, an empty file -- are all
        # ways of losing the check without noticing.
        print("== retrieval         FAILED: no questions were asked")
        return 1
    missed = [(ask, detail) for state, ask, detail in report if state == "miss"]
    gaps = [ask for state, ask, _detail in report if state == "gap"]
    fixed = [ask for state, ask, _detail in report if state == "fixed"]
    found = sum(1 for state, _ask, _d in report if state in {"ok", "fixed"})

    for ask, detail in missed:
        print(f"retrieval no longer answers {ask!r}\n    {detail}")
    for ask in fixed:
        print(f'retrieval now answers {ask!r} -- drop its "gap" note from the list')
    print(
        f"== retrieval         {found}/{len(report)} questions answered"
        f"{f', {len(gaps)} known gap(s)' if gaps else ''}"
    )
    return 1 if missed or fixed else 0


if __name__ == "__main__":
    sys.exit(main())
