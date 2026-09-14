"""Asking Scryfall for one set's printings.

The only module in the project that reaches the network, which is why it is the
only one with a ``Pages`` protocol in front of it: everything downstream reads
a file, and a file is something a test can write.

**One set, not the bulk file.** Scryfall publishes a ``default-cards`` export of
several hundred megabytes covering every card ever printed, and ``jsonstream``
can read it -- but a Beginner Box is 771 printings, which is five requests. The
bulk file is the right tool for "support every set" and the wrong one for
"start playing tonight".

Scryfall asks politely for two things and this does both: a ``User-Agent`` that
says who is calling, and a pause between requests. They are a free service run
for players; the pause is not optional because nobody is enforcing it.
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Protocol, cast

from mtgcoach.carddata.jsondata import MalformedJsonError, require_object

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mtgcoach.carddata.jsondata import JsonObject
    from mtgcoach.core.ids import SetCode

#: Who is calling. Scryfall's documentation asks for something identifying,
#: and an anonymous scraper is how a free service ends up behind a login.
AGENT = "mtgcoach/0.1 (Magic coach for learning at a kitchen table)"

#: Between requests. Scryfall asks for 50-100ms; this is the polite end of it,
#: and five requests at a tenth of a second is not a wait anybody notices.
PAUSE_SECONDS = 0.1

#: How long to wait for one page. Five requests should take under a second;
#: past this something is wrong that waiting will not fix.
READ_TIMEOUT = 30

#: How many pages to follow before deciding something is wrong. A set is five;
#: every card ever printed would be two hundred. A loop in ``next_page`` would
#: otherwise never end.
MAX_PAGES = 60

#: The only host this will open, and only over TLS. ``next_page`` comes out of
#: a response body, so it is not trusted to say where to go next.
HOST = "api.scryfall.com"

_SEARCH = f"https://{HOST}/cards/search"


class ScryfallError(RuntimeError):
    """Scryfall could not be asked, or answered with something unusable."""


class Pages(Protocol):
    """Something that fetches a URL and returns the decoded object."""

    def fetch(self, url: str) -> JsonObject:
        """The JSON object at ``url``.

        Raises:
            ScryfallError: If it cannot be fetched or is not an object.
        """
        ...


class HttpPages:
    """The real thing, over HTTPS, with the pause between requests."""

    def __init__(self, pause: float = PAUSE_SECONDS) -> None:
        """Wait this long before each request after the first."""
        self._pause = pause
        self._asked = False

    def fetch(self, url: str) -> JsonObject:
        """The JSON object at ``url``.

        Raises:
            ScryfallError: If the URL is not Scryfall's, if the request fails,
                or if the answer is not a JSON object.
        """
        _check(url)
        if self._asked:
            time.sleep(self._pause)
        self._asked = True
        try:
            body = self._read(url)
        except (OSError, ValueError) as exc:
            # The class, not the text: a `URLError`'s message carries the whole
            # URL, and this message is printed and logged.
            msg = f"could not reach Scryfall: {type(exc).__name__}"
            raise ScryfallError(msg) from exc
        return _decoded(body)

    def _read(self, url: str) -> str:
        """The response body. Separate so a test can replace the network."""
        request = urllib.request.Request(  # noqa: S310 - scheme and host checked above
            url,
            headers={"User-Agent": AGENT, "Accept": "application/json"},
        )
        with urllib.request.urlopen(request, timeout=READ_TIMEOUT) as answer:  # noqa: S310
            read: bytes = answer.read()
        return read.decode("utf-8", errors="replace")


def _check(url: str) -> None:
    """Refuse anything that is not an HTTPS URL on Scryfall's host.

    ``next_page`` is read out of a response body. Following it blindly is
    following a redirect somebody else chose -- to another host, or to a
    ``file://`` path, which ``urlopen`` will happily read.

    Raises:
        ScryfallError: If the URL is not one to follow.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST:
        msg = f"refusing to fetch {url[:80]!r}: not an https URL on {HOST}"
        raise ScryfallError(msg)


def _decoded(body: str) -> JsonObject:
    """One response, as an object.

    Raises:
        ScryfallError: If it is not JSON, or not an object.
    """
    try:
        return require_object(json.loads(body), "response")
    except (json.JSONDecodeError, ValueError, MalformedJsonError) as exc:
        msg = f"Scryfall's answer was not readable: {exc}"
        raise ScryfallError(msg) from exc


def printings_for(set_code: SetCode, pages: Pages) -> Iterator[JsonObject]:
    """Every printing in a set, a page at a time.

    Raises:
        ScryfallError: If a page cannot be fetched, if Scryfall reports an
            error, or if the pages do not end.
    """
    url = f"{_SEARCH}?{urllib.parse.urlencode({'q': f'set:{set_code}', 'unique': 'prints'})}"
    for _ in range(MAX_PAGES):
        page = pages.fetch(url)
        yield from _cards_in(page, set_code)
        following = page.get("next_page")
        if page.get("has_more") is not True or not isinstance(following, str):
            return
        url = following
    msg = f"Scryfall kept offering more pages of {set_code} past {MAX_PAGES}"
    raise ScryfallError(msg)


def _cards_in(page: JsonObject, set_code: SetCode) -> Iterator[JsonObject]:
    """The card objects on one page.

    Raises:
        ScryfallError: If the page is an error, or has no card list on it. A
            set nobody has heard of comes back as a 404 with ``object:
            "error"``, and reporting "0 cards" for that would send somebody
            looking for a bug in the importer.
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
        if isinstance(entry, dict):
            yield cast("JsonObject", entry)
