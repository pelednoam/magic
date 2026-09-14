"""The address to print, which is not always the address bound to.

``--host 0.0.0.0`` means "every interface", which is not something a phone can
be told. Printing it as ``localhost`` was worse than printing nothing: an
operator copies what is on the screen, and on the phone ``localhost`` is the
phone. The one line they need is the laptop's address on the LAN they are both
on, so this works it out.

A separate module because finding that address is a socket trick with a
paragraph of justification, and ``serve`` is about assembling an app.
"""

from __future__ import annotations

import ipaddress
import socket

#: The hosts that mean "every interface" rather than a place.
WILDCARDS = frozenset({"0.0.0.0", "::", ""})  # noqa: S104 - the LAN is the point

#: Somewhere to ask the routing table about. TEST-NET-1 from RFC 5737, which
#: is reserved for documentation and is not routed anywhere -- and nothing is
#: sent to it regardless, see ``lan_address``.
ELSEWHERE = ("192.0.2.1", 1)

#: What to print when there is no answer. A machine with no route out is a
#: machine whose server nothing else can reach either, so this is honest.
NOWHERE = "localhost"


def reachable(host: str, port: int) -> str:
    """A URL somebody can type on another device, as far as that is knowable."""
    return f"http://{bracketed(host if host not in WILDCARDS else lan_address())}:{port}"


def lan_address() -> str:
    """This machine's address on the network it would route out through.

    A ``connect`` on a UDP socket sends nothing -- it only asks the kernel
    which local address a packet to that destination would leave from, which is
    the answer wanted here. The alternatives are worse: ``gethostname`` returns
    ``127.0.1.1`` on a stock Debian, and enumerating interfaces means picking
    among ``docker0``, ``tailscale0`` and three bridges without knowing which
    one the phone is on.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(ELSEWHERE)
            found: str = probe.getsockname()[0]
    except OSError:
        # No route, no network, or a sandbox that refuses even this. Nothing to
        # print, and nothing to do about it here.
        return NOWHERE
    return found or NOWHERE


def bracketed(host: str) -> str:
    """An IPv6 literal in the brackets a URL needs, anything else unchanged.

    ``http://fe80::1:8000`` is not a URL -- the colons are ambiguous, and every
    client reads it as a host called ``fe80`` on a port that is not a number.
    A hostname is left alone, because brackets around one are just as broken.
    """
    try:
        parsed = ipaddress.ip_address(host)
    except ValueError:
        return host
    return f"[{host}]" if parsed.version == 6 else host  # noqa: PLR2004 - IPv6 is 6
