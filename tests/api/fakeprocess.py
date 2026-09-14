"""Stand-ins for the ``claude`` process, so no test ever starts one.

``Popen`` rather than ``run`` because the module under test needs the process
object: a timed-out ``claude`` has to be killed as a group, and ``run`` only
ever signals the direct child.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Sequence


class Pipe:
    """One of a process's three pipes, as something that can be closed."""

    def __init__(self) -> None:
        """Open."""
        self.closed = False

    def close(self) -> None:
        """Shut. Twice is fine, as it is for a real one."""
        self.closed = True


class Process:
    """A stand-in for the ``claude`` process that answers from memory."""

    def __init__(self, stdout: str, stderr: str, code: int, error: Exception | None) -> None:
        """Reply with this, or fail with that."""
        self._stdout, self._stderr, self._error = stdout, stderr, error
        self.returncode = code
        self.sent = ""
        self.killed = False
        self.pid = 4242
        # The three pipes, as things that can be closed and remember it. The
        # module shuts them on the timeout path, where `communicate` does not.
        self.stdin, self.stdout, self.stderr = Pipe(), Pipe(), Pipe()
        # A timed-out command is still running when it is killed; one that
        # exited has been reaped by `communicate` and must not be.
        self._running = error is not None

    @property
    def closed(self) -> bool:
        """Whether all three pipes were shut."""
        return all(pipe.closed for pipe in (self.stdin, self.stdout, self.stderr))

    def communicate(self, prompt: str, timeout: float | None = None) -> tuple[str, str]:
        """Take the prompt and answer.

        Raises:
            Exception: Whatever this stand-in was built with.
        """
        del timeout
        self.sent = prompt
        if self._error is not None:
            raise self._error
        return self._stdout, self._stderr

    def poll(self) -> int | None:
        """Whether it has exited: None while running, else the exit code."""
        return None if self._running else self.returncode

    def hang(self) -> None:
        """Still running, as a timed-out process is."""
        self._running = True

    def wait(self, timeout: float | None = None) -> int:
        """Reap it."""
        del timeout
        self.killed = True
        return self.returncode


class Fake:
    """A stand-in for ``subprocess.Popen`` that records how it was called."""

    def __init__(self, *, stdout: str = "", stderr: str = "", code: int = 0) -> None:
        """Answer every call with this output."""
        self.process = Process(stdout, stderr, code, None)
        self.argv: tuple[str, ...] = ()
        self.cwd: object = None

    def __call__(self, argv: Sequence[str], **kwargs: object) -> Process:
        """Record the call and return the stand-in process."""
        self.argv = tuple(argv)
        self.cwd = kwargs.get("cwd")
        return self.process

    @property
    def stdin(self) -> str:
        """What was sent to the process."""
        return self.process.sent

    def after(self, flag: str) -> str:
        """The argument following ``flag``."""
        return self.argv[self.argv.index(flag) + 1]


class Raises:
    """A stand-in that fails the way a missing or slow command fails."""

    def __init__(self, error: Exception, *, on_start: bool = False) -> None:
        """Fail with this error, when starting or when talking."""
        self.error = error
        self.on_start = on_start
        #: The process it started, so a test can check what became of it.
        self.started: Process | None = None

    def __call__(self, _argv: Sequence[str], **_kwargs: object) -> Process:
        """Start, or fail to.

        Raises:
            Exception: Whatever this stand-in was built with, if it fails here.
        """
        if self.on_start:
            raise self.error
        self.started = Process("", "", 0, self.error)
        return self.started


class Never:
    """A stand-in that fails the test if the command is run at all."""

    def __call__(self, argv: Sequence[str], **_kwargs: object) -> Process:
        """Never return.

        Raises:
            AssertionError: Always. Being called is the failure.
        """
        msg = f"asked the model about a turn with nothing in it: {argv}"
        raise AssertionError(msg)
