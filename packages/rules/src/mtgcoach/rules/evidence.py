"""The facts a rules question is answered from, as they appear in the prompt.

Split out of ``question``, which was at the line limit and doing two jobs: it
holds the instructions -- what the model is told to *do* -- and this holds the
evidence, which is what it is told. The seam is worth having on its own terms:
every sentence here is a quotation of something (a rule, a card, a board) and
nothing here instructs, so a change to the wording of the instructions cannot
silently change what evidence is supplied.

Four sections, in the order they go in:

1. the retrieved rules, verbatim, with the references that may be cited;
2. the turn -- where in it we are, and what is in hand;
3. the battlefield, as lines, one per permanent;
4. what the cards say, once each, quoted.

Section 4 is the one this module was written for. A question about an ability
used to arrive with the ability flagged and not shown, so "does my Dazzling
Angel gain me life?" was answered from the model's memory of the card. See
``coach.printed`` for what changed and why it is quoted rather than summarised.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from collections.abc import Sequence

    from mtgcoach.coach.printed import PrintedCard
    from mtgcoach.coach.report import TurnReport
    from mtgcoach.coach.table import Table, Thing
    from mtgcoach.rules.corpus import Passage

#: How much card text one prompt may carry, in characters.
#:
#: A number rather than "all of it" because a board is not bounded: the tracker
#: will hold whatever two people put on the table, and a prompt that grows with
#: it gets slower and eventually gets truncated by something that will not say
#: so. The trade is sized off the real set -- Foundations averages 139
#: characters of text a card and its longest is 368 -- so 9,000 is sixty-four
#: average cards or twenty-four of the very longest, against a kitchen-table
#: position of perhaps fifteen distinct cards. Nothing a family plays is cut,
#: and the prompt is bounded whatever a self-play run puts on the table.
#:
#: What is *not* done when the budget runs out is quietly stop. The cards past
#: it are still named, with a line saying their text is not here -- which is
#: the old "read the card" escape hatch, now applied only to the cards it is
#: actually true of.
MOST_CARD_TEXT: Final = 9_000


def rules_found(passages: Sequence[Passage]) -> str:
    """The retrieved rules, verbatim, with the references that may be cited."""
    if not passages:
        return (
            "\nRULES FOUND: none. Nothing in the Comprehensive Rules matched this\n"
            "question, so there is nothing you may cite. Say so in "
            '"unsure" and do\nnot answer from memory.'
        )
    lines = ["\nRULES FOUND (cite the bracketed reference; only these may be cited):"]
    lines.extend(f"  {passage.quoted()}" for passage in passages)
    return "\n".join(lines)


def turn(report: TurnReport) -> str:
    """Where in the turn this is, and what is in hand.

    Less than the turn coach gets. A rules question does not need the mana
    solver's verdicts, and offering them would only invite an answer that leans
    on work the model cannot see.
    """
    whose = "your turn" if report.your_turn else "their turn"
    hand = ", ".join(card.name for card in report.hand) or "nothing"
    lines = [
        (
            f"\nTURN: turn {report.turn}, {report.step.value}, {whose}. "
            f"You are on {report.life} life."
        ),
        f"  In hand: {hand}",
    ]
    if report.unknown:
        lines.append("  The engine cannot read these cards: " + "; ".join(report.unknown))
    return "\n".join(lines)


def battlefield(board: Table) -> str:
    """Both battlefields.

    This is what makes a question about the board answerable at all. Without it
    the prompt's own example -- "Can my creature block that one?" -- had no
    creature and no "that one" in it, and the honest answer to it was a lecture
    about blocking in general.
    """
    return "\n".join(
        ["\nBATTLEFIELD:", *_side("Yours", board.yours), *_side("Theirs", board.theirs)]
    )


def _side(whose: str, things: Sequence[Thing]) -> list[str]:
    """One player's permanents, or a line saying there are none."""
    if not things:
        return [f"  {whose}: nothing on the battlefield."]
    return [f"  {whose}:", *(f"    - {thing.described()}" for thing in things)]


def card_text(cards: Sequence[PrintedCard], budget: int = MOST_CARD_TEXT) -> str:
    """What each card in the position says, quoted, within ``budget``.

    The heading says these are the cards' own words, because the distinction
    between a card's text and a rule's text is one the answer has to keep: a
    citation may only be a rule reference, and a model shown two verbatim
    quotations will otherwise cite the card.
    """
    if not cards:
        return ""
    quoted, cut = _within(cards, budget)
    lines = ["\nWHAT THESE CARDS SAY (the cards' own words; cite rules, not cards):"]
    lines.extend(f"  {card.described()}" for card in quoted)
    if cut:
        lines.append(
            "  These cards are here too and their text is not: "
            + ", ".join(card.name for card in cut)
            + ". Say so and tell the player to read the card."
        )
    return "\n".join(lines)


def _within(
    cards: Sequence[PrintedCard], budget: int
) -> tuple[list[PrintedCard], list[PrintedCard]]:
    """The cards whose text fits, and the cards left over.

    Cut whole cards rather than trimming one. Half an ability reads as a whole
    ability that ends differently, which is a worse thing to put in front of a
    model than a named card with a line saying the text is missing.
    """
    quoted: list[PrintedCard] = []
    spent = 0
    for at, card in enumerate(cards):
        spent += len(card.name) + len(card.text)
        if spent > budget:
            return quoted, list(cards[at:])
        quoted.append(card)
    return quoted, []
