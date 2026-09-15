"""What the cards in this game actually say.

``table`` says what each permanent *is* -- its name, its printed statistics,
whether it is tapped. That was the whole of the board a rules question used to
carry, plus a flag on any card with rules text saying the text existed and was
not being shown. So "does my Dazzling Angel gain me life when I play another
creature?" reached the model as *Dazzling Angel, 2/3, Flying, has rules text
not shown here* -- and the sentence that answers the question, "Whenever
another creature you control enters, you gain 1 life", was nowhere in the
prompt. The answer came from whatever the model remembered about a card with
that name, which is the one thing this project must never do.

This is the other half of the evidence: every distinct card in the position,
once, with its printed text quoted verbatim. Verbatim and not the engine's
model of it -- ``abilities`` exists to be carried out and would have to be
rendered back into prose to go in a prompt, and a paraphrase of a card is the
same failure as a paraphrase of a rule.

**Once each, not once per permanent.** Four Forests on a battlefield are one
card, and printing "({T}: Add {G}.)" four times spends prompt on nothing. The
board lines in ``table`` still name every permanent separately, because two
Bears are two creatures and a question about combat turns on that.

**Whose cards.** Both battlefields, both stacks, and the asking player's own
hand -- nothing this player could not already read off the table. Never the
opponent's hand or either library, which CR 400.2 makes hidden zones: quoting
those into a prompt is cheating, §12 rules it out for good, and the point of
the project is teaching a nine-year-old to play well.

Graveyards are public (CR 400.2) and are left out anyway. A question about a
card in one is real -- "can I get my Bear back?" -- but a graveyard only grows,
so including it would make the prompt grow with the length of the game to quote
cards that are no longer doing anything. If it turns out to be wanted, it is
one line here and a budget already exists to hold it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.coach.lookup import CardLookup
    from mtgcoach.core.cards import CardInstance
    from mtgcoach.core.ids import OracleId, PlayerId
    from mtgcoach.core.state import GameState


@dataclass(frozen=True, slots=True)
class PrintedCard:
    """One card in the position, as printed."""

    name: str
    #: The rules text, verbatim, empty when the card has none printed on it or
    #: the store has never seen it. ``unreadable`` is what tells those apart.
    text: str = ""
    #: Set when the engine cannot carry this card out. Carried here as well as
    #: on the board line because the text and the warning belong together: a
    #: player reading an ability the tracker will not apply needs to be told
    #: so beside the ability, not in a different section.
    unreadable: bool = False

    def described(self) -> str:
        """The card and its text, as a person would read it off the card."""
        said = self.text.strip() or "no rules text on file for this card"
        if self.unreadable:
            return f"{self.name}: {said}\n    (the engine cannot carry this card out)"
        return f"{self.name}: {said}"


def printed(state: GameState, player_id: PlayerId, lookup: CardLookup) -> tuple[PrintedCard, ...]:
    """Every distinct card this player can see, with what it says.

    Ordered battlefields first, then the stack, then hand: a rules question is
    most often about something already in play, and when the text has to be cut
    for length it is the hand that goes last.

    Raises:
        IllegalEventError: If ``player_id`` is not in this game.
    """
    return tuple(
        _card(oracle_id, lookup) for oracle_id in dict.fromkeys(_visible(state, player_id))
    )


def _visible(state: GameState, player_id: PlayerId) -> Iterator[OracleId]:
    """The oracle identity of every card this player may read, with repeats.

    ``dict.fromkeys`` above takes the repeats out while keeping this order, so
    the first place a card appears is where it is listed.
    """
    mine = state.player(player_id)
    for player in state.players.values():
        yield from (permanent.card.oracle_id for permanent in player.battlefield)
    # The stack is one shared, ordered zone (CR 405.1) rather than a tuple per
    # player, and it is read in resolution order -- bottom to top, as it is
    # stored -- so a question about two spells waiting gets them in the order
    # they will happen. This read per player, back when each had its own
    # stack; the two merged cleanly and did not compile, which is the only
    # reason anybody looked.
    yield from (one.card.oracle_id for one in state.stack)
    yield from _ids(mine.hand)


def _ids(cards: tuple[CardInstance, ...]) -> Iterator[OracleId]:
    """The oracle identity of each of these cards."""
    return (card.oracle_id for card in cards)


def _card(oracle_id: OracleId, lookup: CardLookup) -> PrintedCard:
    """One card, named and quoted."""
    return PrintedCard(
        name=lookup.name(oracle_id),
        text=lookup.text(oracle_id),
        unreadable=not lookup.modelled(oracle_id),
    )
