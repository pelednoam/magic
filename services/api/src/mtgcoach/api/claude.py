"""Running the local ``claude`` command, and reading JSON back out of it.

Shared by the turn coach and the rules answerer, which ask different questions
of the same process in the same way. Same choice as the effect extractor: the
command draws on the Claude Code subscription, so neither costs API credits.
§8's cost section prices a turn against the API at about $0.03; the CLI makes
that zero at the price of process startup, which is a second or two. That is
the right trade for a button somebody taps, and the wrong one for something
that fires every step -- which is why both are buttons.

Nothing here decides anything about the game. It runs a subprocess and produces
an object; what may be done with that object is decided by the checkers in
``coach.advice`` and ``rules.answer``.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import ExplainerError

if TYPE_CHECKING:
    from collections.abc import Mapping

#: Tools the command may not use. It is being asked to think about a board, not
#: to touch the repository. The difference between "read the question" and
#: "edit the source" is this line.
FORBIDDEN = "Edit Write MultiEdit NotebookEdit Bash"


@dataclass(frozen=True, slots=True)
class Cli:
    """How to reach the local ``claude`` command."""

    model: str = "opus"
    #: Long enough for a considered answer, short enough that a player taps the
    #: button again rather than wondering whether it is broken.
    timeout_seconds: int = 90
    executable: str = "claude"

    def run(self, prompt: str) -> str:
        """The command's stdout.

        Raises:
            ExplainerError: If the command cannot be run, times out, or fails.
        """
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, prompt via stdin
                [
                    self.executable,
                    "-p",
                    "--output-format",
                    "json",
                    "--model",
                    self.model,
                    "--disallowedTools",
                    FORBIDDEN,
                ],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            msg = f"could not ask the coach: {exc}"
            raise ExplainerError(msg) from exc
        if completed.returncode != 0:
            msg = f"the coach exited {completed.returncode}: {completed.stderr[:200]}"
            raise ExplainerError(msg)
        return completed.stdout


def object_in(stdout: str) -> Mapping[str, object]:
    """The JSON object in the command's output.

    Two envelopes deep: the CLI wraps the model's reply in its own JSON, and the
    reply is itself JSON. Both are unwrapped defensively, because the failure
    mode that matters is a model answering in prose -- which is a thing to
    report, not a thing to guess the meaning of.

    Raises:
        ExplainerError: If there is no object in there.
    """
    payload = _decode(_unwrap(stdout))
    if not isinstance(payload, dict):
        msg = "the coach answered with something that is not an object"
        raise ExplainerError(msg)
    # `json.loads` gives back an unparameterised dict, and strict pyright will
    # not let one through untyped. The cast states what the isinstance above
    # has already established; every field is then checked one at a time.
    return cast("Mapping[str, object]", payload)


def _decode(body: str) -> object:
    """The JSON value in ``body``, whole if it is all JSON, else the object in it.

    The second attempt is what survives a model that wraps its answer in prose
    or a code fence. It is a fallback rather than the first move so that a reply
    which is valid JSON but the *wrong* JSON -- an array of options, say -- is
    reported as the wrong shape instead of being quietly reinterpreted.

    Raises:
        ExplainerError: If neither attempt finds JSON.
    """
    try:
        return json.loads(body)
    except (json.JSONDecodeError, ValueError):
        pass
    start, end = body.find("{"), body.rfind("}")
    if start < 0 or end <= start:
        msg = f"the coach did not answer with an object: {body[:160]!r}"
        raise ExplainerError(msg)
    try:
        return json.loads(body[start : end + 1])
    except (json.JSONDecodeError, ValueError) as exc:
        msg = f"the coach's answer was not readable: {exc}"
        raise ExplainerError(msg) from exc


def _unwrap(stdout: str) -> str:
    """The model's reply, out of the CLI's envelope."""
    try:
        envelope = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return stdout
    if not isinstance(envelope, dict):
        return stdout
    result = cast("Mapping[str, object]", envelope).get("result")
    return result if isinstance(result, str) else stdout


def text(payload: Mapping[str, object], field: str) -> str:
    """A string field, empty when it is missing or the wrong type."""
    value = payload.get(field)
    return value if isinstance(value, str) else ""


def words(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    """A list-of-strings field, keeping only the strings.

    A missing or malformed field is an empty one rather than an error. Nothing
    here is load-bearing for correctness -- the checkers decide whether any of
    it may be shown -- so a bad field is dropped rather than made into a message
    the player would see instead of an answer.
    """
    value = payload.get(field)
    if not isinstance(value, list):
        return ()
    items = cast("list[object]", value)
    return tuple(item for item in items if isinstance(item, str) and item)
