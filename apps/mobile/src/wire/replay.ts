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
 */

import { asObject } from "./shapes";

import type { GameState } from "./board";
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

/** One game out of a journal. */
export interface PlayedGame {
  readonly seed: number;
  readonly decks: readonly string[];
  readonly moments: readonly Moment[];
}

/** The journals this server can show, newest first. */
export interface Journals {
  readonly replays: readonly string[];
}

/** Every game in one journal. */
export interface Walkthrough {
  readonly games: readonly PlayedGame[];
}

/** Whether a body is a walkthrough this app can page through. */
export function isWalkthrough(body: unknown): body is Walkthrough {
  const found = asObject(body);
  return found !== null && Array.isArray(found["games"]);
}

/** Whether a body is the list of journals. */
export function isJournals(body: unknown): body is Journals {
  const found = asObject(body);
  return found !== null && Array.isArray(found["replays"]);
}
