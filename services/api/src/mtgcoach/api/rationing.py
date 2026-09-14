"""How often the two slow routes may be asked, and by how many at once.

Neither is a security boundary. §4 puts this server on one LAN with no auth and
PLAN.md records that as a known gap; nothing here changes it, and a rate limit
in front of an open door is not a lock.

What it is for is the failure that does not need an attacker. Both routes start
a ``claude`` process and spend the operator's subscription, and the client that
calls them is a phone with a button on it. A stuck finger, a reload loop, or a
page left open on a second device is enough to turn "a coach" into "the laptop
is on fire and the quota is gone". A semaphore bounds how many run at once; a
bucket bounds how many run at all.

Per server, not per module, and deliberately not per client: there is no
identity here to key on, and inventing one would be pretending at the auth this
does not have.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

#: How many may be in flight at once. Not sized against the threadpool -- anyio
#: gives it forty workers, which is plenty -- but against the machine: three
#: Node processes thinking at once is what a laptop in a kitchen can carry
#: while still answering the tracker's own routes instantly.
MAX_IN_FLIGHT = 3

#: How many may be started in a window, and how long that window is. Generous
#: for a kitchen table -- a whole game is about fifteen coach taps -- and
#: nowhere near enough to drain a subscription by accident.
BURST = 12
WINDOW_SECONDS = 60.0


@dataclass(slots=True)
class Rationed:
    """The two limits, for one server."""

    in_flight: threading.BoundedSemaphore = field(
        default_factory=lambda: threading.BoundedSemaphore(MAX_IN_FLIGHT)
    )
    burst: int = BURST
    window: float = WINDOW_SECONDS
    _lock: threading.Lock = field(default_factory=threading.Lock)
    #: Tokens left, as a float because it refills continuously.
    _tokens: float = float(BURST)
    _refilled: float = field(default_factory=time.monotonic)

    def take(self) -> str:
        """Take a slot, or say why there is none.

        Returns:
            The empty string when the caller may proceed, and a sentence for
            the player when it may not. A sentence rather than an exception
            because both callers turn it into the same 503, and the interesting
            part is which limit was hit.
        """
        if not self._afford():
            return "that is a lot of questions at once; give it a minute"
        if not self.in_flight.acquire(blocking=False):
            # Put the token back: nothing was spent, and a player who retries
            # in two seconds should not be paying for the attempt that never
            # started.
            self._refund()
            return "the coach is busy with another question; try again in a moment"
        return ""

    def release(self) -> None:
        """Give back a slot taken by ``take``."""
        self.in_flight.release()

    def _afford(self) -> bool:
        """Whether there is a token, refilling first."""
        with self._lock:
            now = time.monotonic()
            self._tokens = min(
                float(self.burst),
                self._tokens + (now - self._refilled) * self.burst / self.window,
            )
            self._refilled = now
            if self._tokens < 1.0:
                return False
            self._tokens -= 1.0
            return True

    def _refund(self) -> None:
        """Return a token taken for a call that never ran."""
        with self._lock:
            self._tokens = min(float(self.burst), self._tokens + 1.0)
