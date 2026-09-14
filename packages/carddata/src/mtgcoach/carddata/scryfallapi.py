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
        yield from _cards_in(page, set_code)
        # The envelope, before its pagination is trusted. `_cards_in` refuses an
        # `object: "error"` page and a page with no card list, which leaves one
        # shape still getting through: something that is neither a list nor an
        # error -- a proxy's JSON, a single card object -- whose `has_more` is
        # simply absent.
        if page.get("object") != "list":
            msg = f"Scryfall's answer for {set_code} was not a list of cards"
            raise ScryfallError(msg)
        # `is not True` read a *missing* or corrupted `has_more` as "that was
        # the last page", so a truncated or rewritten envelope ended the
        # download and wrote a short file that imported cleanly. Absent is not
        # the same as false, and only Scryfall saying `false` ends this.
        more = page.get("has_more")
        if not isinstance(more, bool):
            msg = f"Scryfall's {set_code} page did not say whether there were more"
            raise ScryfallError(msg)
        if not more:
            return
        following = page.get("next_page")
        if not isinstance(following, str):
            # It said there was more and did not say where. Returning here
            # looked like a finished download and wrote a short file that
            # imported cleanly -- a set quietly missing its last four hundred
            # printings, which nothing downstream could notice.
            msg = f"Scryfall said there were more {set_code} printings but not where"
            raise ScryfallError(msg)
        url = following
    msg = f"Scryfall kept offering more pages of {set_code} past {MAX_PAGES}"
    raise ScryfallError(msg)


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
