"""The Comprehensive Rules, as passages that can be quoted.

The document is one long text file with a rigid shape, which is the only reason
this is worth parsing rather than embedding whole: 2,700 numbered passages and
a glossary, each individually addressable. A question about trample can be
answered with rule 702.19b in front of it, verbatim, rather than from whatever
a model remembers about trample.

That is the point of the whole module. §8 says a confidently wrong rule is
worse than no answer, and the way to keep that promise is to never ask for a
rule from memory -- to retrieve the text, put it in the prompt, and then check
that the answer cites something that was actually there.

The parse is deliberately shallow. It does not model the rules; it finds their
boundaries, so that each one can be found again by number.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum

#: A numbered rule or subrule: ``100.1.``, ``702.19b``, ``104.3a``. Section
#: heads (``100. General``) share the leading digits and are told apart by the
#: absence of a subrule part, which ``_TITLE`` then confirms.
_NUMBERED = re.compile(r"^(\d{3}(?:\.\d+)?[a-z]?)\.?\s+(\S.*)$")

#: A heading rather than a rule: short, and with none of the punctuation a
#: sentence needs. "Trample" and "Brawl Option" are headings; "An ability can
#: be one of three things:" is a rule that happens to end in a colon.
_TITLE = re.compile(r"^[^.:;,]{1,60}$")

#: Where the glossary begins, the second time this word appears alone on a line
#: -- the first is the table of contents.
_GLOSSARY = "Glossary"

#: The line that ends the glossary, again on its second appearance.
_CREDITS = "Credits"


class Kind(Enum):
    """Where a passage came from. Both are quotable; they read differently."""

    RULE = "rule"
    GLOSSARY = "glossary"


@dataclass(frozen=True, slots=True)
class Passage:
    """One quotable piece of the rules."""

    #: How to cite it: "702.19b", or a term for a glossary entry.
    reference: str
    #: The heading it sits under, for context. "Trample", "Combat Damage Step".
    title: str
    text: str
    kind: Kind

    def quoted(self) -> str:
        """The passage as it should appear in a prompt.

        The reference goes in square brackets and nothing else does, because a
        model shown ``702.19b (Trample):`` cites ``702.19b (Trample)`` -- which
        is the right rule under a name the checker has never heard of, and the
        answer is thrown away for being decorated rather than for being wrong.
        Asking for the bracketed token is the version that survives.
        """
        under = "glossary" if self.kind is Kind.GLOSSARY else self.title
        named = f" ({under})" if under else ""
        return f"[{self.reference}]{named} {self.text}"


def passages_in(document: str) -> tuple[Passage, ...]:
    """Every rule and glossary entry in the Comprehensive Rules.

    Raises:
        CorpusError: If the document does not have the shape of the rules.
    """
    lines = document.replace("\r\n", "\n").split("\n")
    start, glossary, end = _bounds(lines)
    return (*_rules(lines[start:glossary]), *_glossary(lines[glossary:end]))


class CorpusError(ValueError):
    """The document is not the Comprehensive Rules."""


def _bounds(lines: list[str]) -> tuple[int, int, int]:
    """Where the rules begin, where the glossary begins, and where it ends.

    The document is: front matter, a table of contents ending with the word
    "Credits", the numbered rules, the glossary, and a credits page. So the
    rules start one line after the contents end, and each of the other two
    markers is found by its *second* appearance -- the first is the contents
    entry naming it, and taking that one made the whole document look like one
    enormous glossary.

    Raises:
        CorpusError: If a marker is missing or they are out of order.
    """
    contents = _nth(lines, _CREDITS, 0)
    glossary = _nth(lines, _GLOSSARY, 1)
    end = _nth(lines, _CREDITS, 1)
    if not 0 <= contents < glossary < end:
        msg = "this document is not the Comprehensive Rules"
        raise CorpusError(msg)
    return contents + 1, glossary, end


def _nth(lines: list[str], marker: str, index: int) -> int:
    """Where the ``index``-th line that is exactly ``marker`` is, or -1."""
    found = [at for at, line in enumerate(lines) if line.strip() == marker]
    return found[index] if len(found) > index else -1


def _rules(lines: list[str]) -> tuple[Passage, ...]:
    """The numbered rules, each under the heading it belongs to."""
    found: list[Passage] = []
    title = ""
    for line in lines:
        match = _NUMBERED.match(line.strip())
        if match is None:
            continue
        reference, text = match.group(1), match.group(2).strip()
        if _TITLE.match(text):
            title = text
            continue
        found.append(Passage(reference, title, text, Kind.RULE))
    return tuple(found)


def _glossary(lines: list[str]) -> tuple[Passage, ...]:
    """The glossary, as term and definition.

    An entry is a term on its own line followed by its definition, which runs
    until the next blank line. Multi-line definitions are joined with a space
    rather than kept as lines, because what goes in a prompt is a paragraph.
    """
    found: list[Passage] = []
    term = ""
    body: list[str] = []
    for line in lines[1:]:
        stripped = line.strip()
        if not stripped:
            _keep(found, term, body)
            term, body = "", []
        elif not term:
            term = stripped
        else:
            body.append(stripped)
    _keep(found, term, body)
    return tuple(found)


def _keep(found: list[Passage], term: str, body: list[str]) -> None:
    """Add one glossary entry, if there is one."""
    if term and body:
        found.append(Passage(term, term, " ".join(body), Kind.GLOSSARY))
