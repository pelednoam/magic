/**
 * The shape the server sends, written out to match `services/api/views.py`.
 *
 * Hand-written, like the Python side it mirrors, and for the same reason: the
 * wire is a contract two people agreed on, not a dump of either side's types.
 * `tests/api/test_wire_contract.py` reads this file and fails if the server
 * starts sending a field this does not know about, which is the drift that
 * would otherwise be found by a blank space in the UI.
 *
 * Nothing here interprets anything. `reasons` are sentences the engine wrote
 * and this app prints; it does not know what a land is, and must not learn.
 */

/** One card in hand, and the engine's verdict on it. */
export interface Playable {
  readonly instance_id: string;
  readonly name: string;
  /**
   * Whether playing this is a land drop. The two actions are different events,
   * and only one of them exists yet -- the engine cannot record *casting* a
   * spell, so a client that treats every playable card as a land drop sends an
   * illegal event for every spell the coach just said you can afford.
   */
  readonly is_land: boolean;
  readonly playable: boolean;
  /** Empty when playable. Otherwise the engine's own words, printed verbatim. */
  readonly reasons: readonly string[];
  readonly payment: Payment | null;
}

/** Which sources to tap, and -- the useful half -- which to keep up. */
export interface Payment {
  readonly tap: readonly string[];
  readonly keep: readonly string[];
}

/** One attack and what the opponent's best answer does to it. */
export interface Plan {
  /** What to call them on screen. Two creatures can share a name. */
  readonly attackers: readonly string[];
  /** What to key a list on. Two creatures cannot share an identity. */
  readonly attacker_ids: readonly string[];
  readonly damage: number;
  readonly defender_life_after: number;
  readonly lethal: boolean;
  readonly you_lose: readonly string[];
  readonly they_lose: readonly string[];
  readonly you_gain: number;
  readonly they_gain: number;
}

/** The attacks worth making, or the sentence saying why there are none. */
export interface Attacks {
  readonly plans: readonly Plan[];
  /** Empty when there are plans; otherwise why the section is empty. */
  readonly unavailable: string;
  /**
   * What is on the table that the numbers do not account for. Not a reason to
   * hide the plans -- they are still the best available -- but the player has
   * to read "four damage, lethal" as "unless the Pacifism says otherwise".
   */
  readonly caveats: readonly string[];
}

/** A trigger the player is about to miss. */
export interface Reminder {
  readonly instance_id: string;
  readonly name: string;
  readonly event: string;
}

/** Everything the coach has to say about this moment, for one player. */
export interface Advice {
  readonly turn: number;
  readonly step: string;
  readonly your_turn: boolean;
  readonly life: number;
  readonly hand: readonly Playable[];
  readonly attacks: Attacks;
  readonly reminders: readonly Reminder[];
  /** Cards the coach cannot speak for. Shown, never hidden. */
  readonly unknown: readonly string[];
}

/** One card, by both of its identities and the word printed on it. */
export interface Card {
  readonly instance_id: string;
  readonly oracle_id: string;
  readonly name: string;
}

/** One permanent, with the two states a tracker has to show. */
export interface Permanent extends Card {
  readonly tapped: boolean;
  readonly summoning_sick: boolean;
}

/** One player's half of the board. The library is a count, never a list. */
export interface Player {
  readonly life: number;
  readonly library: number;
  readonly lands_played_this_turn: number;
  readonly hand: readonly Card[];
  readonly battlefield: readonly Permanent[];
  readonly graveyard: readonly Card[];
  readonly exile: readonly Card[];
}

/** The board, as much of it as a client may see. */
export interface GameState {
  readonly turn: number;
  readonly step: string;
  readonly active_player: string;
  readonly players: Readonly<Record<string, Player>>;
}

/** What every route returns: the board, plus advice for both players. */
export interface Snapshot {
  /**
   * How many events this game has seen. Monotonic, and the only ordering the
   * client has: HTTP replies and socket broadcasts arrive in whatever order
   * the network chooses, and without this an older one silently won.
   */
  readonly version: number;
  readonly state: GameState;
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
  if (body === null || typeof body["version"] !== "number") {
    return false;
  }
  const state = asObject(body["state"]);
  const advice = asObject(body["advice"]);
  if (state === null || advice === null) {
    return false;
  }
  // Down to what the screen actually dereferences. Checking only that `state`
  // is an object let `{state: {}}` through, and the crash arrived one render
  // later inside `snapshot.state.players[YOU]` -- far from the frame that
  // caused it, which is the worst place for a type error to surface.
  const players = asObject(state["players"]);
  return players !== null && hasSeats(players) && hasSeats(advice);
}

/** Both seats present, because the screen reads both. */
function hasSeats(value: Record<string, unknown>): boolean {
  return asObject(value[YOU]) !== null && asObject(value[THEM]) !== null;
}

/**
 * A plain object, or null.
 *
 * Arrays are excluded: `typeof [] === "object"` and `[] !== null`, so the
 * looser check accepted a JSON array as a snapshot.
 */
function asObject(value: unknown): Record<string, unknown> | null {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return null;
  }
  return value as Record<string, unknown>;
}
