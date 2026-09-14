"""The HTTPS client, and the two things it refuses to do.

Separate from ``scryfallapi`` because that module is about what to ask Scryfall
for and this one is about the wire. It is also the only code in the project
that opens a socket to the internet, which is reason enough for it to be one
short file somebody can read in full.

The refusals both come from the same fact: ``next_page`` is read out of a
response body, so where to go next is not ours to decide.

- ``_check`` allows only HTTPS on Scryfall's host. ``urlopen`` will read a
  ``file://`` path perfectly happily.
- ``CheckedRedirects`` puts a redirect through ``_check`` as well. Without it
  the first hop was guarded and every hop after it was not -- which is exactly
  the "redirect somebody else chose" the module claimed to refuse, and its own
  docstring was wrong about it.

And two courtesies Scryfall asks for and nobody enforces: a ``User-Agent`` that
says who is calling, and a pause between requests.
"""

from __future__ import annotations

import time
import urllib.parse
import urllib.request
from typing import TYPE_CHECKING, Protocol, override

from mtgcoach.carddata.scryfallapi import HOST, ScryfallError, decoded

if TYPE_CHECKING:
    from typing import IO

    from mtgcoach.carddata.jsondata import JsonObject

#: Who is calling. Scryfall's documentation asks for something identifying,
#: and an anonymous scraper is how a free service ends up behind a login.
AGENT = "mtgcoach/0.1 (Magic coach for learning at a kitchen table)"

#: Between requests. Scryfall asks for 50-100ms; this is the polite end of it,
#: and five requests at a tenth of a second is not a wait anybody notices.
PAUSE_SECONDS = 0.1

#: How long to wait for one page. Five requests should take under a second;
#: past this something is wrong that waiting will not fix.
READ_TIMEOUT = 30


class Opener(Protocol):
    """The part of ``urllib``'s opener this uses."""

    def open(self, request: urllib.request.Request, timeout: float) -> IO[bytes]:
        """The response, as something with a ``read``."""
        ...


class CheckedRedirects(urllib.request.HTTPRedirectHandler):
    """A redirect handler that puts the new URL through ``_check`` too."""

    @override
    def redirect_request(
        self,
        req: urllib.request.Request,
        fp: object,
        code: int,
        msg: str,
        headers: object,
        newurl: str,
    ) -> urllib.request.Request | None:
        """The next request, if the place it points to is allowed.

        Raises:
            ScryfallError: If the redirect leaves Scryfall or drops TLS.
        """
        _check(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)  # type: ignore[arg-type]


class HttpPages:
    """The real thing, over HTTPS, with the pause between requests."""

    def __init__(self, pause: float = PAUSE_SECONDS, opener: Opener | None = None) -> None:
        """Wait this long before each request after the first.

        ``opener`` defaults to one whose redirect handler re-checks the host.
        A parameter so a test can hand over something that does not open a
        socket, rather than reaching into this module to replace it.
        """
        self._pause = pause
        self._opener = opener if opener is not None else _checked_opener()
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
        return decoded(body)

    def _read(self, url: str) -> str:
        """The response body. Separate so a test can replace the network."""
        request = urllib.request.Request(  # noqa: S310 - scheme and host checked above
            url,
            headers={"User-Agent": AGENT, "Accept": "application/json"},
        )
        with self._opener.open(request, timeout=READ_TIMEOUT) as answer:
            read: bytes = answer.read()
        return read.decode("utf-8", errors="replace")


def _checked_opener() -> urllib.request.OpenerDirector:
    """An opener whose redirects go back through ``_check``."""
    return urllib.request.build_opener(CheckedRedirects)


def _check(url: str) -> None:
    """Refuse anything that is not an HTTPS URL on Scryfall's host.

    Raises:
        ScryfallError: If the URL is not one to follow.
    """
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != "https" or parsed.hostname != HOST:
        msg = f"refusing to fetch {url[:80]!r}: not an https URL on {HOST}"
        raise ScryfallError(msg)
