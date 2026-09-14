"""The address printed at startup, which is not the address bound to.

`--host 0.0.0.0` is "every interface", and printing that as `localhost` was
worse than printing nothing: the operator copies what is on the screen, and on
the phone `localhost` is the phone. These pin the three ways that goes wrong.
"""

from __future__ import annotations

import socket
from typing import TYPE_CHECKING, Self, override

if TYPE_CHECKING:
    from collections.abc import Callable

import pytest

from mtgcoach.api.address import NOWHERE, bracketed, lan_address, reachable


@pytest.mark.parametrize("wildcard", ["0.0.0.0", "::", ""])  # noqa: S104 - the point
def test_a_wildcard_host_is_printed_as_this_machines_lan_address(
    wildcard: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nobody can type "every interface" into a phone."""

    def found(_family: socket.AddressFamily) -> str:
        """A plausible LAN address, whichever family was asked for."""
        return "192.168.1.42"

    monkeypatch.setattr("mtgcoach.api.address.lan_address", found)
    assert reachable(wildcard, 8000) == "http://192.168.1.42:8000"


def test_a_host_that_was_asked_for_is_printed_as_asked_for() -> None:
    """`--host` naming one interface is already an answer."""
    assert reachable("10.0.0.5", 8000) == "http://10.0.0.5:8000"


def test_a_named_host_is_left_alone() -> None:
    assert reachable("laptop.local", 8000) == "http://laptop.local:8000"


def test_an_ipv6_host_is_bracketed() -> None:
    """An unbracketed v6 literal is not a URL.

    Every client reads `http://fe80::1:8000` as a host called `fe80` on a port
    that is not a number.
    """
    assert reachable("fe80::1", 8000) == "http://[fe80::1]:8000"


@pytest.mark.parametrize("host", ["10.0.0.5", "laptop.local", "localhost"])
def test_brackets_go_on_nothing_else(host: str) -> None:
    """Not on a hostname.

    Brackets around one are just as broken as no brackets around a v6 literal.
    """
    assert bracketed(host) == host


def test_the_lan_address_is_the_one_a_packet_would_leave_from() -> None:
    """Not asserted as a value -- it is whatever this machine's is.

    But it must be an address, and it must not be the loopback that
    `gethostname` gives on a stock Debian.
    """
    found = lan_address()
    assert found == NOWHERE or not found.startswith("127."), found


def test_a_machine_with_no_route_out_says_so_instead_of_failing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A container with no network, or a sandbox that refuses a UDP connect.

    There is nothing to print and nothing to do about it here, and a traceback
    instead of a server would be the worst of the three.
    """

    class Refusing(_Probe):
        """A socket that will not connect."""

        @override
        def connect(self, _where: tuple[str, int]) -> None:
            """Refuse.

            Raises:
                OSError: Always.
            """
            msg = "network is unreachable"
            raise OSError(msg)

    monkeypatch.setattr(socket, "socket", _made(Refusing()))
    assert lan_address() == NOWHERE


def test_a_kernel_that_answers_with_nothing_says_so(monkeypatch: pytest.MonkeyPatch) -> None:
    """Not seen in the wild, but `getsockname` is typed as returning `Any`.

    An empty host printed into a URL would point nowhere in particular rather
    than fail obviously.
    """

    class Blank(_Probe):
        """A socket that connects and knows no address."""

        @override
        def getsockname(self) -> tuple[str, int]:
            """An address that is not one."""
            return ("", 0)

    monkeypatch.setattr(socket, "socket", _made(Blank()))
    assert lan_address() == NOWHERE


class _Probe:
    """Enough of a socket for `lan_address`, as a context manager.

    The base answers correctly; each test overrides the one method it is about.
    """

    def __enter__(self) -> Self:
        """Enter the block."""
        return self

    def __exit__(self, *_exit: object) -> None:
        """Leave it."""

    def connect(self, _where: tuple[str, int]) -> None:
        """Succeed without sending anything, which is what the real one does."""

    def getsockname(self) -> tuple[str, int]:
        """A plausible LAN address."""
        return ("192.168.1.42", 0)


def _made(probe: _Probe) -> Callable[[int, int], _Probe]:
    """A `socket.socket` that hands back this, whatever it was asked for."""

    def opened(_family: int, _kind: int) -> _Probe:
        return probe

    return opened
