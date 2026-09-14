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

import subprocess
import tempfile
from dataclasses import dataclass

from mtgcoach.coach.advice import ExplainerError

#: The tools the command may use: none.
#:
#: An empty allow-list, not a deny-list. The deny-list this replaced named the
#: five write tools and left Read, Glob, Grep, WebFetch, WebSearch and Task
#: enabled -- so the comment above it ("not to touch the repository") was true
#: about writing and false about everything else. An allow-list cannot rot that
#: way: a tool added to the CLI next month is not on it either.
NO_TOOLS = ""


@dataclass(frozen=True, slots=True)
class Cli:
    """How to reach the local ``claude`` command."""

    model: str = "opus"
    #: Long enough for a considered answer, short enough that a player taps the
    #: button again rather than wondering whether it is broken.
    timeout_seconds: int = 90
    executable: str = "claude"
    #: Where the subprocess runs. Defaults to a directory that holds nothing.
    working_directory: str = tempfile.gettempdir()

    def run(self, prompt: str) -> str:
        """The command's stdout.

        Raises:
            ExplainerError: If the command cannot be run, times out, or fails.
        """
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, prompt via stdin, no shell
                [
                    self.executable,
                    "-p",
                    "--output-format",
                    "json",
                    "--model",
                    self.model,
                    "--tools",
                    NO_TOOLS,
                    # And no MCP servers either. `--tools ""` empties the
                    # built-in set; a project or user MCP config would put a
                    # fresh set back, and this process inherits the operator's.
                    "--strict-mcp-config",
                ],
                input=prompt,
                capture_output=True,
                text=True,
                # Pinned, not inherited. `text=True` alone encodes stdin with
                # the ambient locale codec, so a card name or a question with a
                # non-ASCII character in it raised UnicodeEncodeError on a
                # POSIX-locale server -- and Magic prints em-dashes.
                encoding="utf-8",
                errors="replace",
                timeout=self.timeout_seconds,
                check=False,
                # Its own process group, so the timeout kills the whole tree.
                # `claude` is a Node process that spawns more; killing only the
                # direct child left them running, still holding the quota and
                # still writing, after the request had already failed.
                start_new_session=True,
                # Somewhere with nothing in it. The file tools are gone, but a
                # working directory is also what the CLI puts in its own system
                # prompt, and the server's tree is not the model's business.
                cwd=self.working_directory,
            )
        except subprocess.TimeoutExpired as timed_out:
            msg = f"the coach took longer than {self.timeout_seconds}s"
            raise ExplainerError(msg) from timed_out
        except (OSError, subprocess.SubprocessError) as exc:
            # The exception's text, not the command's: `FileNotFoundError` says
            # what is missing without quoting anything the model produced.
            msg = f"could not ask the coach: {type(exc).__name__}"
            raise ExplainerError(msg) from exc
        if completed.returncode != 0:
            # Deliberately without stderr. This message reaches the client, and
            # the CORS policy is `*` -- a CLI's stderr carries absolute paths,
            # config locations and sometimes an account, none of which is any
            # origin's business. The exit code is what a player can act on.
            msg = f"the coach exited {completed.returncode}"
            raise ExplainerError(msg)
        return completed.stdout
