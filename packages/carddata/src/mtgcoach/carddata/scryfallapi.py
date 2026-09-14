"""Asking Scryfall for one set's printings.

The ``Pages`` protocol is the seam: this module knows what to ask for and how
to read the answer, ``scryfallhttp`` knows how to fetch it, and everything
downstream reads a file -- which is something a test can write.

**One set, not the bulk file.** Scryfall publishes a ``default-cards`` export of
several hundred megabytes covering every card ever printed, and ``jsonstream``
can read it -- but a Beginner Box is 771 printings, which is five requests. The
bulk file is the right tool for "support every set" and the wrong one for
"start playing tonight".

Everything here fails loudly. This is an *import*: a page that is not quite
what it should be is worth stopping over, because the alternative is a database
that is wrong in a way nobody finds until a game.
"""

from __future__ import annotations

import json
import urllib.parse
from typing import TYPE_CHECKING, Protocol, cast

from mtgcoach.carddata.jsondata import MalformedJsonError, require_object

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.carddata.jsondata import JsonObject
    from mtgcoach.core.ids import SetCode

#: How many pages to follow before deciding something is wrong. A set is five;
#: every card ever printed would be two hundred. A loop in ``next_page`` would
#: otherwise never end.
MAX_PAGES = 60

#: The only host the client will open, and only over TLS. Here rather than in
#: ``scryfallhttp`` because ``next_page`` is read out of a body this module
#: parses, so both halves need to agree on what counts as Scryfall.
HOST = "api.scryfall.com"

_SEARCH = f"https://{HOST}/cards/search"


class ScryfallError(RuntimeError):
    """Scryfall could not be asked, or answered with something unusable."""


class Pages(Protocol):
    """Something that fetches a URL and returns the decoded object.

    The seam between "what to ask for" and "how to fetch it". Only
    ``scryfallhttp`` opens a socket; a test hands over something that does not.
    """

    def fetch(self, url: str) -> JsonObject:
        """The JSON object at ``url``.

        Raises:
            ScryfallError: If it cannot be fetched or is not an object.
        """
        ...


def decoded(body: str) -> JsonObject:
    """One response body, as an object.

    Raises:
        ScryfallError: If it is not JSON, or is not an object.
    """
    try:
        loaded = json.loads(body)
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"Scryfall's answer was not readable: {exc}"
        raise ScryfallError(msg) from exc
    try:
        return require_object(loaded, "response")
    except MalformedJsonError as exc:
        msg = f"Scryfall's answer was not readable: {exc}"
        raise ScryfallError(msg) from exc


def printings_for(set_code: SetCode, pages: Pages) -> Iterator[JsonObject]:
    """Every printing in a set, a page at a time.

    Raises:
        ScryfallError: If a page cannot be fetched, if Scryfall reports an
            error, if a page is not a list, if it does not say whether there
            are more, if it offers more pages without saying where, or if the
            pages do not end.
    """
    url = f"{_SEARCH}?{urllib.parse.urlencode({'q': f'set:{set_code}', 'unique': 'prints'})}"
    for _ in range(MAX_PAGES):
        page = pages.fetch(url)
        # Every check on the envelope happens *before* a single card is handed
        # out. This generator is lazy, so a consumer that takes one card and
        # stops -- or writes as it goes -- used to receive and keep cards from
        # a page these checks would have refused, and might never reach the
        # refusal at all. `sets_fetch` happens to drain it into a list, which
        # is exactly the kind of thing that stops being true later.
        following = _pagination_of(page, set_code)
        yield from _cards_in(page, set_code)
        if following is None:
            return
        url = following
    msg = f"Scryfall kept offering more pages of {set_code} past {MAX_PAGES}"
    raise ScryfallError(msg)


def _pagination_of(page: JsonObject, set_code: SetCode) -> str | None:
    """Where the next page is, or None if this was the last.

    *Every* question about the envelope is settled here, before a single card
    is handed out. This generator is lazy: a consumer that takes one card and
    stops -- or writes as it goes -- used to receive cards from a page whose
    ``next_page`` these checks would have refused, and might never reach the
    refusal at all. ``sets_fetch`` happens to drain it into a list, which is
    exactly the kind of thing that stops being true later.

    Raises:
        ScryfallError: If the page is not a card list, does not say whether
            there are more, or says there are and not where. Each used to end
            the download quietly: `is not True` read a *missing* or corrupted
            ``has_more`` as "that was the last page", and a missing
            ``next_page`` looked like a finished download -- a set quietly
            short of its last four hundred printings, which nothing downstream
            could notice.

            The ``object`` check catches the one shape ``_cards_in`` lets
            through: something that is neither a list nor an error, like a
            proxy's own JSON or a single card object, whose ``has_more`` is
            simply not there.
    """
    if page.get("object") == "error":
        # Left to `_cards_in`, which has the error's own text to quote.
        return None
    if page.get("object") != "list":
        msg = f"Scryfall's answer for {set_code} was not a list of cards"
        raise ScryfallError(msg)
    more = page.get("has_more")
    if not isinstance(more, bool):
        msg = f"Scryfall's {set_code} page did not say whether there were more"
        raise ScryfallError(msg)
    if not more:
        return None
    following = page.get("next_page")
    # An empty string is not a location. It used to be accepted and then
    # refused one layer down as "not an https URL", which is a true sentence
    # about the wrong thing.
    if not isinstance(following, str) or not following.strip():
        msg = f"Scryfall said there were more {set_code} printings but not where"
        raise ScryfallError(msg)
    return following


def _cards_in(page: JsonObject, set_code: SetCode) -> Iterator[JsonObject]:
    """The card objects on one page.

    Raises:
        ScryfallError: If the page is an error, has no card list on it, or
            carries something that is not a card. A set nobody has heard of
            comes back as a 404 with ``object: "error"``, and reporting "0
            cards" for that would send somebody looking for a bug in the
            importer.
    """
    if page.get("object") == "error":
        detail = page.get("details")
        said = detail if isinstance(detail, str) else "no such set"
        msg = f"Scryfall has no printings for {set_code}: {said}"
        raise ScryfallError(msg)
    data = page.get("data")
    if not isinstance(data, list):
        msg = f"Scryfall's answer for {set_code} had no card list in it"
        raise ScryfallError(msg)
    for entry in cast("list[object]", data):
        if not isinstance(entry, dict):
            # Skipping it was a quiet way to lose a card.
            msg = f"Scryfall's {set_code} page carried something that is not a card"
            raise ScryfallError(msg)
        yield cast("JsonObject", entry)
