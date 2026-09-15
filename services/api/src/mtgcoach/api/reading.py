"""Reading a game line back out of a journal.

Split from ``recording`` at the line limit, and the seam is writing against
reading -- the same one ``journal`` and ``answers`` have on the harness side.

Everything here is suspicious of what it is given. A journal is a file that a
process may have been killed part-way through writing, so a line can be short,
truncated, or half a card. The rule throughout is that a damaged deal is
*refused*, never repaired: dropping one card shifts every card after it, and
the game that rebuilds then has different hands and different draws from the
one that was played, with nothing on screen saying so.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

from mtgcoach.api.eventspec import parse
from mtgcoach.api.recording import CARD_FIELDS, KIND, Recording

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence

    from mtgcoach.core.events import Event


def recorded(line: object) -> Recording | None:
    """One journal line as a recording, or None if it is not one."""
    if not isinstance(line, dict):
        return None
    loaded = cast("dict[str, object]", line)
    if loaded.get("kind") != KIND:
        return None
    seed, decks = loaded.get("seed"), loaded.get("decks")
    first, libraries = loaded.get("first"), loaded.get("libraries")
    if not isinstance(seed, int) or not isinstance(first, str):
        return None
    if not isinstance(decks, list) or not isinstance(libraries, dict):
        return None
    named = cast("list[object]", decks)
    return Recording(
        seed=seed,
        game=str(loaded.get("game", "")),
        decks=(str(named[0]), str(named[-1])) if named else ("", ""),
        first=first,
        libraries=_libraries(cast("dict[str, object]", libraries)),
        events=_events(loaded.get("events")),
    )


def _libraries(loaded: Mapping[str, object]) -> dict[str, tuple[tuple[str, str], ...]]:
    """Each seat's dealt library, from a decoded line.

    Raises:
        ValueError: If any entry is not a card. Dropping one and carrying on
            shifts every card after it, so the game that rebuilds is a game
            that never happened -- the hands are different, the draws are
            different, and nothing on screen says so. A game the screen refuses
            to show is much the better failure.
    """
    return {seat: _cards(seat, cards) for seat, cards in loaded.items()}


def _cards(seat: str, loaded: object) -> tuple[tuple[str, str], ...]:
    """One seat's library.

    Raises:
        ValueError: If it is not a list of id-and-oracle pairs.
    """
    if not isinstance(loaded, list):
        # ValueError, not TypeError: this is a value off a disk that is the
        # wrong shape, not a caller passing the wrong argument, and every
        # reader of a journal catches ValueError for exactly that reason.
        msg = f"{seat}: a library is a list of cards, not {type(loaded).__name__}"
        raise ValueError(msg)  # noqa: TRY004 - a bad file, not a bad call
    made = [_card(seat, card) for card in cast("list[object]", loaded)]
    seen = {instance for instance, _ in made}
    if len(seen) != len(made):
        # Two cards with one identity is not a deck. `InstanceId` exists so
        # that "the Mountain you tapped" is a different card from the other
        # one, and every zone movement is looked up by it -- so a duplicate
        # would make one of them unreachable and the other ambiguous.
        msg = f"{seat}: two cards share an instance id"
        raise ValueError(msg)
    return tuple(made)


def _card(seat: str, loaded: object) -> tuple[str, str]:
    """One card: its instance id and its oracle id.

    Both required to be non-empty strings rather than coerced with ``str``,
    which turned ``[null, 3]`` into the perfectly usable-looking card
    ``("None", "3")`` and dealt it into a game.

    Raises:
        ValueError: If it is not a pair of non-empty strings.
    """
    if not isinstance(loaded, list) or len(cast("list[object]", loaded)) != CARD_FIELDS:
        msg = f"{seat}: a card is an instance id and an oracle id, got {loaded!r}"
        raise ValueError(msg)
    pair = cast("Sequence[object]", loaded)
    if not all(isinstance(one, str) and one for one in pair):
        msg = f"{seat}: a card's two ids must both be non-empty strings, got {loaded!r}"
        raise ValueError(msg)
    return (str(pair[0]), str(pair[1]))


def _events(loaded: object) -> tuple[Event, ...]:
    """Every event, in order, skipping anything unreadable.

    A journal is written by a process that can be killed, so a truncated tail
    is a real shape. Dropping one event silently would rebuild a *wrong* board,
    which is worse than a short one -- so this stops at the first bad entry
    rather than skipping past it.
    """
    if not isinstance(loaded, list):
        return ()
    kept: list[Event] = []
    for entry in cast("list[object]", loaded):
        if not isinstance(entry, dict):
            break
        try:
            kept.append(parse(cast("dict[str, object]", entry)))
        except ValueError:
            break
    return tuple(kept)
