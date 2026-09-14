"""Running the local ``claude`` command.

Shared by the turn coach and the rules answerer, which ask different questions
of the same process in the same way. Reading an object back out of what it
printed is ``replies``. Same choice as the effect extractor: the
command draws on the Claude Code subscription, so neither costs API credits.
§8's cost section prices a turn against the API at about $0.03; the CLI makes
that zero at the price of process startup, which is a second or two. That is
the right trade for a button somebody taps, and the wrong one for something
that fires every step -- which is why both are buttons.

Nothing here decides anything about the game. It runs a subprocess and returns
what it printed.

**The subprocess gets no tools at all.** That is not caution, it is the only
safe setting: a rules question is text a player typed, arriving over an
unauthenticated route, and it ends up inside this prompt. A model with Read and
WebFetch in that position is a file-read primitive and an egress primitive in
one session, on a machine holding the operator's Claude Code credentials. It
was verified rather than assumed -- with tools on, the same prompt read
``/etc/hostname`` and returned its contents; with ``--tools ""`` it could not,
and made something up instead, which is the failure mode we want.
"""

from __future__ import annotations

import atexit
import os
import shutil
import signal
import subprocess
import tempfile
from contextlib import contextmanager, suppress
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING

from mtgcoach.coach.advice import ExplainerError

if TYPE_CHECKING:
    from collections.abc import Generator

#: The tools the command may use: none.
#:
#: An empty allow-list, not a deny-list. The deny-list this replaced named the
#: five write tools and left Read, Glob, Grep, WebFetch, WebSearch and Task
#: enabled -- so the comment above it ("not to touch the repository") was true
#: about writing and false about everything else. An allow-list cannot rot that
#: way: a tool added to the CLI next month is not on it either.
NO_TOOLS = ""


@cache
def _scratch() -> Path:
    """An empty directory only this user can write to.

    Not ``gettempdir()`` itself. The CLI reads a ``CLAUDE.md`` from its working
    directory and treats it as instructions, so running in the shared temp
    directory let any local user drop one there and have it prepended to every
    question this server asks. ``mkdtemp`` is 0700 and unguessable, which
    closes it; made once per process because the directory is a constant.
    """
    made = Path(tempfile.mkdtemp(prefix="mtgcoach-coach-"))
    # Every run would otherwise leave one behind. It is empty and 0700, so the
    # cost is an inode, but a server restarted nightly for a year is 365 of
    # them and somebody eventually has to wonder what they are.
    atexit.register(lambda: shutil.rmtree(made, ignore_errors=True))
    return made


@dataclass(frozen=True, slots=True)
class Cli:
    """How to reach the local ``claude`` command."""

    model: str = "opus"
    #: Long enough for a considered answer, short enough that a player taps the
    #: button again rather than wondering whether it is broken.
    timeout_seconds: int = 90
    executable: str = "claude"
    #: Where the subprocess runs. Defaults to a private empty directory made
    #: for this process; see ``_scratch``.
    working_directory: str = field(default_factory=lambda: str(_scratch()))

    def run(self, prompt: str) -> str:
        """The command's stdout.

        Raises:
            ExplainerError: If the command cannot be run, times out, or fails.
        """
        try:
            with self._started() as process:
                stdout, _ = self._talk(process, prompt)
        except (OSError, subprocess.SubprocessError) as exc:
            # The exception's class, not its text: `FileNotFoundError` says what
            # is missing without quoting a path into a response any origin can
            # read.
            msg = f"could not ask the coach: {type(exc).__name__}"
            raise ExplainerError(msg) from exc
        return stdout

    @contextmanager
    def _started(self) -> Generator[subprocess.Popen[str]]:
        """The command, running, killed as a group however the block ends.

        ``Popen`` rather than ``run`` because of that last part. ``run``'s
        timeout path calls ``process.kill()``, which signals the direct child
        and nothing else; ``start_new_session=True`` puts the child in its own
        process group but ``run`` never signals the group. So a timed-out
        ``claude`` -- a Node process that spawns more -- left its children
        alive, still holding the quota and still writing, after the request had
        already failed. ``killpg`` is the part that was missing.
        """
        process = subprocess.Popen(  # noqa: S603 - fixed argv, prompt via stdin, no shell
            self._argv(),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            # Pinned, not inherited. `text=True` alone encodes stdin with the
            # ambient locale codec, so a card name or a question with a
            # non-ASCII character in it raised UnicodeEncodeError on a
            # POSIX-locale server -- and Magic prints em-dashes.
            encoding="utf-8",
            errors="replace",
            # Somewhere with nothing in it. The file tools are gone, but a
            # working directory is also what the CLI puts in its own system
            # prompt, and the server's tree is not the model's business.
            cwd=self.working_directory,
            start_new_session=True,
        )
        try:
            yield process
        finally:
            _kill_group(process)

    def _argv(self) -> list[str]:
        """The command line. Fixed; nothing from a player reaches it."""
        return [
            self.executable,
            "-p",
            "--output-format",
            "json",
            "--model",
            self.model,
            "--tools",
            NO_TOOLS,
            # And no MCP servers either. `--tools ""` empties the built-in set;
            # a project or user MCP config would put a fresh set back, and this
            # process inherits the operator's.
            "--strict-mcp-config",
        ]

    def _talk(self, process: subprocess.Popen[str], prompt: str) -> tuple[str, str]:
        """Send the prompt, read the reply.

        Raises:
            ExplainerError: If it takes too long or exits non-zero.
        """
        try:
            stdout, stderr = process.communicate(prompt, timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired as timed_out:
            msg = f"the coach took longer than {self.timeout_seconds}s"
            raise ExplainerError(msg) from timed_out
        if process.returncode != 0:
            # Deliberately without stderr. This message reaches the client, and
            # the CORS policy is `*` -- a CLI's stderr carries absolute paths,
            # config locations and sometimes an account, none of which is any
            # origin's business. The exit code is what a player can act on.
            msg = f"the coach exited {process.returncode}"
            raise ExplainerError(msg)
        return stdout, stderr


def _kill_group(process: subprocess.Popen[str]) -> None:
    """End the command and everything it started.

    The group is signalled whether or not the direct process is still running.
    Skipping it when the parent had exited was the original bug wearing a
    different hat: ``claude`` is a Node process that spawns more, and a parent
    that has returned says nothing about its children -- which would then sit
    there holding the quota with nobody waiting on them.

    Best effort otherwise: an ``ESRCH`` here means the group is already gone,
    which is the ordinary case and not worth turning a finished answer into an
    error over.
    """
    with suppress(OSError):
        os.killpg(os.getpgid(process.pid), signal.SIGKILL)
    with suppress(OSError, ValueError, subprocess.TimeoutExpired):
        process.wait(timeout=5)
