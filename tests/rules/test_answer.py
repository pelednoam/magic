"""Checking a rules answer against the rules it was given.

Weaker than the turn coach's check, and honest about it: this cannot tell
whether the model read 509.1a correctly, only whether it is quoting something
nobody gave it. That is what a confidently wrong rules answer looks like from
the outside, and it is the failure §8 says must never reach a child.
"""

from __future__ import annotations

from helpers_rules import PASSAGES
from mtgcoach.rules.answer import Answer, cited, refusal, settle, verify
from mtgcoach.rules.corpus import Kind, Passage

TRAMPLE = [p for p in PASSAGES if p.reference in {"702.19b", "Trample"}]


def _said(**fields: object) -> Answer:
    """An answer that is fine except for what the test changes."""
    base: dict[str, object] = {
        "answer": "Trample assigns lethal damage to the blocker first.",
        "in_short": "The extra damage goes through.",
        "citations": ("702.19b",),
    }
    return Answer(**{**base, **fields})  # type: ignore[arg-type]


def test_an_answer_citing_a_rule_it_was_given_passes() -> None:
    assert cited(_said(), TRAMPLE)


def test_an_answer_citing_a_rule_it_was_not_given_is_not() -> None:
    """The shape a remembered rule takes: real-looking, and not in the prompt."""
    problems = verify(_said(citations=("509.1a",)), TRAMPLE)
    assert problems
    assert "509.1a" in problems[0]


def test_every_invented_citation_is_named() -> None:
    problems = verify(_said(citations=("702.19b", "104.3a", "999.9z")), TRAMPLE)
    assert "104.3a, 999.9z" in problems[0]
    assert "702.19b" not in problems[0]


def test_an_answer_with_no_words_is_refused() -> None:
    assert "says nothing" in verify(_said(answer="", in_short=""), TRAMPLE)


def test_the_child_sentence_alone_is_enough_to_have_said_something() -> None:
    assert cited(_said(answer=""), TRAMPLE)


def test_an_answer_with_nothing_to_look_up_is_refused() -> None:
    """An uncited answer is fluent, plausible, and impossible to check."""
    problems = verify(_said(citations=()), TRAMPLE)
    assert "no rule to look up" in problems[0]


def test_a_real_citation_is_not_treated_as_proof_of_the_claim() -> None:
    """The limit of this check, written down so nobody mistakes it for more.

    "Trample doubles all damage [702.19b]" cites a rule that was retrieved and
    says no such thing. It passes, and it has to -- nothing here reads the
    rule. That is exactly why the wire field is `cited` and not `trusted`, and
    why the retrieved rules are printed under every answer.
    """
    wrong = _said(answer="Trample doubles all damage.", citations=("702.19b",))
    assert cited(wrong, TRAMPLE)


def test_admitting_doubt_does_not_excuse_an_uncited_claim() -> None:
    """The hole this closed: a confident paragraph with a disclaimer stapled on.

    `unsure` used to exempt an answer from citing anything, so
    "trample doubles all damage" plus unsure="one minor detail" passed. The
    admission has to be the whole answer, not a footnote to one.
    """
    assert not cited(_said(citations=(), unsure="one minor detail"), TRAMPLE)


def test_an_answer_that_cites_nothing_never_passes() -> None:
    """However it is dressed, and whatever was retrieved."""
    assert not cited(_said(citations=()), TRAMPLE)
    assert not cited(_said(citations=()), [])
    assert not cited(_said(citations=(), unsure="nothing matched"), [])


def test_the_refusal_says_what_went_wrong_without_repeating_the_answer() -> None:
    refused = refusal(["cites rules it was not given: 999.9z"])
    assert "not shown" in refused.answer
    assert "999.9z" in refused.unsure
    assert refused.citations == ()


# --- citations as a model actually writes them --------------------------------


def _settled(*citations: str) -> Answer:
    """The answer, with its citations resolved against the trample passages."""
    resolved, _ = settle(_said(citations=citations), TRAMPLE)
    return resolved


def test_a_citation_copied_with_its_title_still_names_the_rule() -> None:
    """What the live model did on the first try, for every single answer."""
    assert cited(_settled("702.19b (Trample)"), TRAMPLE)
    assert _settled("702.19b (Trample)").citations == ("702.19b",)


def test_the_word_rule_in_front_comes_off() -> None:
    assert _settled("rule 702.19b").citations == ("702.19b",)
    assert _settled("Rule 702.19b").citations == ("702.19b",)


def test_brackets_copied_out_of_the_prompt_come_off() -> None:
    assert _settled("[702.19b]").citations == ("702.19b",)


def test_trailing_punctuation_comes_off() -> None:
    assert _settled("702.19b.").citations == ("702.19b",)


def test_a_glossary_term_cited_in_the_wrong_case_still_matches() -> None:
    assert _settled("trample").citations == ("Trample",)


def test_the_same_rule_written_two_ways_is_cited_once() -> None:
    """Two spellings of one rule is one rule, not a list with a repeat in it."""
    assert _settled("702.19b", "rule 702.19b (Trample)").citations == ("702.19b",)


def test_resolving_does_not_make_a_different_rule_match() -> None:
    """The decoration comes off; the digits do not. This is the whole check."""
    resolved, problems = settle(_said(citations=("702.19c (Trample)",)), TRAMPLE)
    assert resolved.citations == ("702.19c (Trample)",)
    assert problems


def test_an_invented_rule_survives_resolving_and_is_reported() -> None:
    _, problems = settle(_said(citations=("999.9z (Trample)",)), TRAMPLE)
    assert "999.9z" in problems[0]


def test_settling_an_answer_that_was_already_right_changes_nothing() -> None:
    resolved, problems = settle(_said(), TRAMPLE)
    assert resolved == _said()
    assert problems == ()


def test_two_supplied_references_that_normalise_alike_are_left_alone() -> None:
    """Resolving takes decoration off, so it can in principle merge two of them.

    Picking one would rewrite a citation into a rule the model did not name.
    Left as written, it either matches something exactly or is reported.
    """
    twins = [
        Passage("702.19b", "Trample", "text", Kind.RULE),
        Passage("702.19b (Trample)", "Trample", "text", Kind.RULE),
    ]
    resolved, problems = settle(_said(citations=("702.19b (Trample)",)), twins)
    assert resolved.citations == ("702.19b (Trample)",)
    assert problems == ()
