"""Asking Claude, through the local CLI rather than the API.

Same choice as the effect extractor: the ``claude`` command draws on the Claude
Code subscription, so a turn's advice costs nothing per call. §8's cost section
prices this against the API at about $0.03 a turn; the CLI makes that zero at
the price of process startup, which is a second or two. That is the right trade
for a button somebody taps when they want help, and the wrong one for something
that fires every step -- which is why it is a button.

Nothing here decides anything about the game. It builds a prompt from the
engine's report, runs a subprocess, and parses what comes back into an
``Explanation`` that ``advice.verify`` then checks against the engine. A failure
at any point is an ``ExplainerError``: the deterministic panel is already on
screen, already right, and already free.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from mtgcoach.coach.advice import ExplainerError, Explanation

if TYPE_CHECKING:
    from collections.abc import Mapping

    from mtgcoach.coach.report import TurnReport


@dataclass(frozen=True, slots=True)
class ClaudeCliExplainer:
    """An explainer backed by the local ``claude`` command."""

    model: str = "opus"
    #: Long enough for a considered answer, short enough that a player taps the
    #: button again rather than wondering whether it is broken.
    timeout_seconds: int = 90
    executable: str = "claude"

    def explain(self, report: TurnReport, briefing: str) -> Explanation:
        """Advise on this turn.

        Raises:
            ExplainerError: If the command fails, times out, or answers with
                something that is not the agreed object.
        """
        idle = _nothing_to_say(report)
        return idle if idle is not None else parse(self._run(briefing))

    def _run(self, briefing: str) -> str:
        """The command's stdout, or an error saying why there is none."""
        try:
            completed = subprocess.run(  # noqa: S603 - fixed argv, prompt via stdin
                [
                    self.executable,
                    "-p",
                    "--output-format",
                    "json",
                    "--model",
                    self.model,
                    # It is being asked to think, not to act. The diff between
                    # "read the board" and "edit the repository" is this line.
                    "--disallowedTools",
                    "Edit Write MultiEdit NotebookEdit Bash",
                ],
                input=briefing,
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


def _nothing_to_say(report: TurnReport) -> Explanation | None:
    """The answer to a turn with no decision in it, or None if there is one.

    Draw steps, upkeeps and a hand of uncastable cards are most of a game, and
    asking a model "which of these zero options is best" costs a subprocess and
    a quota call to be told what the report already says. Only taken when the
    engine understood everything on the table: with anything under CANNOT SPEAK
    FOR there *is* something to say, and saying it is the model's job.
    """
    decisions = any(card.playable for card in report.hand) or report.attacks.plans
    if decisions or report.unknown or report.attacks.caveats:
        return None
    return Explanation(
        because="Nothing here can be played or attacked with, so the turn just moves on.",
        in_short="Nothing to do right now -- pass the turn.",
    )


def parse(stdout: str) -> Explanation:
    """Turn the command's output into an explanation.

    Two envelopes deep: the CLI wraps the model's reply in its own JSON, and the
    reply is itself JSON. Both are unwrapped defensively, because the failure
    mode that matters is a model answering in prose -- which is a thing to
    report, not a thing to guess the meaning of.

    Raises:
        ExplainerError: If there is no usable answer in there.
    """
    payload = _decode(_unwrap(stdout))
    if not isinstance(payload, dict):
        msg = "the coach answered with something that is not an object"
        raise ExplainerError(msg)
    # `json.loads` gives back an unparameterised dict, and strict pyright will
    # not let one through untyped. The cast states what the isinstance above
    # has already established; every field is then checked one at a time.
    explanation = _explanation(cast("Mapping[str, object]", payload))
    if not explanation.because and not explanation.in_short:
        # Reached by the CLI's own error envelope, whose `result` is null: that
        # decodes to a well-formed object with none of the fields in it. Advice
        # with no words is not advice, and showing it blank would look like the
        # coach had considered the board and had nothing to say.
        msg = "the coach's answer had no explanation in it"
        raise ExplainerError(msg)
    return explanation


def _decode(body: str) -> object:
    """The JSON value in ``body``, whole if it is all JSON, else the object in it.

    The second attempt is what survives a model that wraps its answer in prose
    or a code fence. It is a fallback rather than the first move so that a
    reply which is valid JSON but the *wrong* JSON -- an array of options, say
    -- is reported as the wrong shape instead of being quietly reinterpreted.

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


def _explanation(payload: Mapping[str, object]) -> Explanation:
    """Build an explanation, taking only fields of the right shape.

    A missing field is an empty one. Nothing here is load-bearing for
    correctness -- ``advice.verify`` decides whether any of it may be shown --
    so a malformed field is dropped rather than made into an error the player
    would see instead of advice.
    """
    return Explanation(
        play=_text(payload, "play"),
        attack=_words(payload, "attack"),
        because=_text(payload, "because"),
        in_short=_text(payload, "in_short"),
        watch_out=_words(payload, "watch_out"),
        check_yourself=_words(payload, "check_yourself"),
    )


def _text(payload: Mapping[str, object], field: str) -> str:
    """A string field, empty when it is missing or the wrong type."""
    value = payload.get(field)
    return value if isinstance(value, str) else ""


def _words(payload: Mapping[str, object], field: str) -> tuple[str, ...]:
    """A list-of-strings field, keeping only the strings."""
    value = payload.get(field)
    if not isinstance(value, list):
        return ()
    items = cast("list[object]", value)
    return tuple(item for item in items if isinstance(item, str) and item)
