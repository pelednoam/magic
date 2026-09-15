/**
 * The payload every route returns, and the check that it is one.
 *
 * Split from `board.ts` at the length limit, and the seam is a real one: that
 * file is what the engine *computed* about a position, and this is the
 * envelope it arrives in -- which board, for which seat, produced under which
 * versions, and how to tell a real one from whatever a fetch happened to
 * decode.
 */

import { asObject } from "./shapes";

import type { Advice } from "./board";
import type { GameState, Sources } from "./game";

/** What every route returns: the board, plus this device's own advice. */
export interface Snapshot {
  /**
   * How many events this game has seen. Monotonic, and the only ordering the
   * client has: HTTP replies and socket broadcasts arrive in whatever order
   * the network chooses, and without this an older one silently won.
   */
  readonly version: number;
  /**
   * Whether this server can answer rules questions.
   *
   * The Comprehensive Rules are an optional install. False means the question
   * box has nothing behind it, and saying so up front beats letting somebody
   * type a question and wait for a 503.
   */
  readonly rules_available: boolean;
  /**
   * Which seat this payload is for: the server's answer, from the token the
   * request carried. It used to be chosen here — start a game and you were
   * "you", join one and you were "them" — and a device set to the wrong seat
   * was a device acting as the other player.
   */
  readonly seat: string;
  /** What produced this board. See `Sources`. */
  readonly sources: Sources;
  readonly state: GameState;
  /**
   * The coach's view, under this device's own seat and no other: one entry,
   * keyed by `seat`. It used to hold both players', and an `Advice` names
   * every card in the hand it is about — so that was the opponent's hand
   * arriving twice over, once in the board and once here.
   */
  readonly advice: Readonly<Record<string, Advice>>;
}

/** A new game also says what to call it. */
export interface NewGame extends Snapshot {
  readonly session_id: string;
}

/** The two seats. The server names them, and this app only ever displays them. */
export const YOU = "you";
export const THEM = "them";

/**
 * Whether a decoded response is shaped like a snapshot.
 *
 * A cast is a claim, not a check: `JSON.parse(...) as Snapshot` accepted `null`
 * and any object without `state`, and the crash arrived one render later at
 * `snapshot.state.players`, far from the frame that caused it. This is the
 * boundary, so this is where the claim gets tested.
 */
export function isSnapshot(value: unknown): value is Snapshot {
  const body = asObject(value);
  if (
    body === null ||
    typeof body["version"] !== "number" ||
    typeof body["rules_available"] !== "boolean"
  ) {
    return false;
  }
  const state = asObject(body["state"]);
  const advice = asObject(body["advice"]);
  if (state === null || advice === null || typeof body["seat"] !== "string") {
    return false;
  }
  // Down to what the screen actually dereferences. Checking only that `state`
  // is an object let `{state: {}}` through, and the crash arrived one render
  // later inside `snapshot.state.players[YOU]` -- far from the frame that
  // caused it, which is the worst place for a type error to surface.
  const players = asObject(state["players"]);
  return players !== null && hasSeats(players) && asObject(advice[body["seat"]]) !== null;
}

/**
 * Both seats present in the *board*, because the screen reads both halves of
 * it — two battlefields, two life totals, two hand counts.
 *
 * The advice is not checked this way: there is one entry and it is the seat
 * the payload names, which is checked against that name rather than against
 * these two constants.
 */
function hasSeats(value: Record<string, unknown>): boolean {
  return asObject(value[YOU]) !== null && asObject(value[THEM]) !== null;
}
