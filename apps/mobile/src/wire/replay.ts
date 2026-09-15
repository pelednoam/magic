/**
 * A played game, as the server serves it for stepping through.
 *
 * Written out to match `services/api/walking.py`, like the rest of this folder.
 *
 * Every field here describes something that *already happened*: the board comes
 * from the recorded events of a real game and the advice from what the coach
 * actually said at the time. Nothing is re-asked, so nothing shown here can
 * differ from what happened — which is the point of walking a game with
 * somebody who is learning the rules from it.
 *
 * A game is addressed by `index`, its position in the journal. Two runs into
 * one journal repeat a seed, so a seed is a label and not an address.
 */

import { asObject } from "./shapes";

import type { GameState } from "./game";
import type { Explanation } from "./claude";

/** One decision: where in the game, the board, and what was said about it. */
export interface Moment {
  readonly turn: number;
  /** The step's own name, printed as-is. */
  readonly step: string;
  /** Which seat was asked. */
  readonly player: string;
  readonly state: GameState;
  /** Null when the coach had no answer at all — a real moment, still shown. */
  readonly said: Explanation | null;
  /** Whether the engine agreed with it, checked when it was given. */
  readonly trusted: boolean;
  /** The engine's objections, when it did not. */
  readonly problems: readonly string[];
  /** Why there was no answer, when there was none. */
  readonly error: string;
}

/** One line in a journal's list of games. No boards: see `read_replay`. */
export interface GameLine {
  /** Its position in the journal, which is its address. */
  readonly index: number;
  /** What re-runs it. A label here, because two runs can repeat one. */
  readonly seed: number;
  readonly decks: readonly string[];
  readonly decisions: number;
}

/** One game, with every moment of it. */
export interface PlayedGame extends GameLine {
  readonly moments: readonly Moment[];
}

/** The journals this server can show, newest first. */
export interface Journals {
  readonly replays: readonly string[];
}

/** What is in one journal. */
export interface Walkthrough {
  readonly games: readonly GameLine[];
}

/** Whether a body lists the games in a journal. */
export function isWalkthrough(body: unknown): body is Walkthrough {
  const found = asObject(body);
  return found !== null && Array.isArray(found["games"]) && found["games"].every(isGameLine);
}

/** Whether a body is the list of journals. */
export function isJournals(body: unknown): body is Journals {
  const found = asObject(body);
  return (
    found !== null && Array.isArray(found["replays"]) && found["replays"].every(isString)
  );
}

/**
 * Whether a body is a game this app can step through.
 *
 * Down to what the screen actually dereferences, like `isSnapshot` and for the
 * same reason: checking only that `moments` is an array let a moment without a
 * board through, and the crash arrived one render later inside
 * `moment.state.players`, far from the frame that caused it.
 */
export function isPlayedGame(body: unknown): body is PlayedGame {
  const found = asObject(body);
  return (
    found !== null &&
    isGameLine(found) &&
    Array.isArray(found["moments"]) &&
    found["moments"].every(isMoment)
  );
}

function isGameLine(value: unknown): boolean {
  const line = asObject(value);
  return (
    line !== null &&
    typeof line["index"] === "number" &&
    typeof line["seed"] === "number" &&
    Array.isArray(line["decks"]) &&
    line["decks"].every(isString)
  );
}

function isMoment(value: unknown): boolean {
  const one = asObject(value);
  if (one === null || typeof one["turn"] !== "number" || typeof one["step"] !== "string") {
    return false;
  }
  const players = asObject(asObject(one["state"])?.["players"]);
  return players !== null && Array.isArray(one["problems"]);
}

function isString(value: unknown): boolean {
  return typeof value === "string";
}
