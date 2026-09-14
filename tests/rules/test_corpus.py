"""Finding the boundaries of 3,500 rules in one text file.

The parse is shallow on purpose -- it does not model the rules, it finds where
each one starts and stops so it can be quoted and cited. These check the two
things that actually go wrong: a heading read as a rule, and the table of
contents read as the document.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from mtgcoach.rules.corpus import CorpusError, Kind, Passage, passages_in

EXCERPT = Path(__file__).resolve().parents[1] / "fixtures" / "rules_excerpt.txt"


def _passages() -> tuple[Passage, ...]:
    return passages_in(EXCERPT.read_text(encoding="utf-8"))


def _by_reference(reference: str) -> Passage:
    found = [p for p in _passages() if p.reference == reference]
    assert len(found) == 1, f"{reference}: {len(found)} matches"
    return found[0]


def test_a_subrule_keeps_its_number_and_its_heading() -> None:
    passage = _by_reference("702.19b")
    assert passage.title == "Trample"
    assert passage.text.startswith("The controller of an attacking creature")
    assert passage.kind is Kind.RULE


def test_a_top_level_rule_is_a_passage_too() -> None:
    assert _by_reference("100.1").text.startswith("These Magic rules apply")


def test_a_heading_is_not_a_rule() -> None:
    """A section head such as 702.19 names the section; it is not a rule."""
    assert not [p for p in _passages() if p.text == "Trample" and p.kind is Kind.RULE]


def test_a_heading_that_reads_like_a_title_is_still_a_heading() -> None:
    """Brawl Option has no sentence punctuation, which is how it is known."""
    assert not [p for p in _passages() if p.reference == "903.12" and p.kind is Kind.RULE]


def test_a_rule_ending_in_a_colon_is_a_rule() -> None:
    """The heading test is punctuation, not length -- a colon means a sentence."""
    document = _shaped("100.1. There are three of these:")
    (passage,) = [p for p in passages_in(document) if p.reference == "100.1"]
    assert passage.text.endswith("these:")


def test_the_contents_is_not_mistaken_for_the_document() -> None:
    """Every marker appears twice; taking the first made the parse nonsense."""
    assert len(_passages()) > 1
    assert not [p for p in _passages() if p.text.startswith("Declare Blockers")]


def test_the_glossary_comes_through_as_terms() -> None:
    passage = _by_reference("Deathtouch")
    assert passage.kind is Kind.GLOSSARY
    assert "lethal" in passage.text


def test_a_definition_spanning_lines_becomes_one_paragraph() -> None:
    """What goes in a prompt is a paragraph, not a column."""
    passage = _by_reference("Trample")
    assert passage.kind is Kind.GLOSSARY
    assert "combat damage. See rule 702.19" in passage.text


def test_a_rule_quotes_itself_with_the_reference_in_brackets() -> None:
    """The brackets are what the model is told to cite, and only that."""
    assert _by_reference("702.19b").quoted().startswith("[702.19b] (Trample) The controller")


def test_a_glossary_entry_says_it_is_one() -> None:
    assert _by_reference("Deathtouch").quoted().startswith("[Deathtouch] (glossary) A keyword")


def test_a_rule_with_no_heading_still_quotes() -> None:
    """Before the first heading there is nothing to put in the parentheses."""
    assert Passage("1.1", "", "text", Kind.RULE).quoted() == "[1.1] text"


def _shaped(*body: str) -> str:
    """A document with the markers in the right places and ``body`` between."""
    return "\n".join(["Contents", "Glossary", "Credits", "", *body, "", "Glossary", "", "Credits"])


def test_a_document_that_is_not_the_rules_is_refused() -> None:
    with pytest.raises(CorpusError, match="not the Comprehensive Rules"):
        passages_in("some other document entirely")


def test_a_document_with_the_markers_in_the_wrong_order_is_refused() -> None:
    """Glossary before the contents end is the table of contents, not a body."""
    with pytest.raises(CorpusError, match="not the Comprehensive Rules"):
        passages_in("Glossary\nGlossary\nCredits\nCredits")


def test_a_glossary_entry_with_no_definition_is_dropped() -> None:
    """A stray term with nothing under it is a page artefact, not an entry."""
    document = _shaped("100.1. A rule.").replace(
        "\nGlossary\n\nCredits", "\nGlossary\n\nStray\n\nReal\nA definition.\n\nCredits"
    )
    glossary = [p for p in passages_in(document) if p.kind is Kind.GLOSSARY]
    assert [p.reference for p in glossary] == ["Real"]


def test_a_glossary_entry_at_the_very_end_is_kept() -> None:
    """The last entry has no blank line after it, so it needs its own flush."""
    document = _shaped("100.1. A rule.").replace(
        "\nGlossary\n\nCredits", "\nGlossary\n\nLast\nA definition.\nCredits"
    )
    assert [p.reference for p in passages_in(document) if p.kind is Kind.GLOSSARY] == ["Last"]


# --- a rule is not always one line --------------------------------------------


def test_an_example_belongs_to_the_rule_above_it() -> None:
    """An example is part of its rule, and 211 rules in the document have one.

    For a beginner the example is often the only usable part. Dropping them
    made a passage labelled verbatim quietly incomplete -- the worst thing to
    be wrong about in a design that rests on quoting the rules.
    """
    assert "Example: a game with three players" in _by_reference("100.1").text


def test_a_continuation_paragraph_belongs_to_the_rule_above_it() -> None:
    passage = _by_reference("100.1a")
    assert passage.text.startswith("A two-player game")
    assert passage.text.endswith("options in section 8.")


def test_a_continuation_is_joined_as_a_paragraph_not_kept_as_lines() -> None:
    """What goes in a prompt is a paragraph; the line breaks are typesetting."""
    assert "\n" not in _by_reference("100.1a").text


def test_a_chapter_heading_ends_the_rule_before_it() -> None:
    """Without this, "8. Multiplayer Rules" became the last sentence of 903.12."""
    assert not [p for p in _passages() if p.text.endswith("Multiplayer Rules")]


def test_a_rule_after_a_chapter_heading_is_still_found() -> None:
    assert _by_reference("800.1").text.startswith("A multiplayer game")


def test_the_last_rule_before_the_glossary_is_not_lost() -> None:
    """It is flushed by the end of the loop rather than by the next rule."""
    assert _by_reference("800.1").kind is Kind.RULE


def test_text_before_the_first_rule_is_not_attached_to_anything() -> None:
    """A stray line above the first numbered rule belongs to no rule at all."""
    document = _shaped("some preamble", "100.1. A rule.")
    (passage,) = [p for p in passages_in(document) if p.kind is Kind.RULE]
    assert passage.text == "A rule."
