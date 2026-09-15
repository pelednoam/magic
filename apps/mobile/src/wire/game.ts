/**
 * The board itself: zones, permanents, and how the game ended.
 *
 * Split from `board.ts` at the length limit, and the seam is a real one — this
 * is the *game's* shape and that file is the *coach's*. A client reads both in
 * one payload, and they are written by different halves of the project.
 *
 * Hand-written to match `services/api/boardview.py`, like the rest of this
 * folder. `tests/api/test_wire_contract.py` reads every file here and fails if
 * the server starts sending a field none of them knows about.
 */

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

/**
 * One player's half of the board. The library is a count, never a list.
 *
 * No stack here, and there used to be. It was a list per player, which gave
 * two devices two orders and no way to agree which spell resolves first
 * (CR 405.5); it is one ordered list on `GameState` now.
 */
export interface Player {
  readonly life: number;
  readonly library: number;
  readonly lands_played_this_turn: number;
  readonly hand: readonly Card[];
  readonly battlefield: readonly Permanent[];
  readonly graveyard: readonly Card[];
  readonly exile: readonly Card[];
}

/** One spell waiting to resolve, on the one stack both players share. */
export interface Waiting extends Card {
  /** Whose spell it is (CR 405.4). A shared zone has to say. */
  readonly controller: string;
  /**
   * Where this resolves to — `battlefield` for a permanent spell (CR 608.3),
   * `graveyard` for an instant or a sorcery (CR 608.2m), null for a card the
   * coach cannot identify.
   *
   * The server read the type line and sent the answer, because `resolve_spell`
   * has to carry it and the engine holds no card data. The app used to
   * remember it from the hand advice and send it back after the card had left
   * the zone it read it from; now it never has to know.
   */
  readonly resolves_to: string | null;
}

/** One player who is out of the game, and why. */
export interface Lost {
  readonly player: string;
  /** The engine's own reason: `life` (CR 704.5a) or `empty_library` (704.5b). */
  readonly why: string;
}

/**
 * How the game ended.
 *
 * `winner` is null on a draw, which is a real outcome (CR 104.4b) and not a
 * missing answer — so `drawn` says which, rather than leaving a null to be
 * read as "we do not know".
 */
export interface Over {
  readonly lost: readonly Lost[];
  readonly winner: string | null;
  readonly drawn: boolean;
}

/** The board, as much of it as a client may see. */
export interface GameState {
  readonly turn: number;
  readonly step: string;
  readonly active_player: string;
  readonly players: Readonly<Record<string, Player>>;
  /**
   * Every spell waiting to resolve, bottom first (CR 405.2). The screen shows
   * it the other way up, because the thing that happens next belongs at the
   * top of a list a person reads.
   */
  readonly stack: readonly Waiting[];
  /**
   * Who may act (CR 117.1), or null when nobody may — the untap and cleanup
   * steps, and the moment after everybody has passed, when the top of the
   * stack resolves or the step ends (CR 117.4).
   *
   * Whose *turn* it is (`active_player`) is a different question, and the app
   * only had that one: a player may cast an instant on their opponent's turn,
   * and all of answering a spell happens while it is somebody else's.
   */
  readonly priority: string | null;
  /** Who has passed since the last action (CR 117.4's "in succession"). */
  readonly passed: readonly string[];
  /** Who still has to pass before anything happens, in the order they act. */
  readonly yet_to_pass: readonly string[];
  /**
   * Null while the game is going.
   *
   * The app had no way to know a game had ended, so it carried on offering
   * plays to a player who had already lost — and the server accepted them.
   */
  readonly over: Over | null;
}
