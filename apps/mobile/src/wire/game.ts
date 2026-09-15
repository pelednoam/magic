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

/** One player's half of the board. The library is a count, never a list. */
export interface Player {
  readonly life: number;
  readonly library: number;
  readonly lands_played_this_turn: number;
  readonly hand: readonly Card[];
  /** Spells cast and not yet resolved. Public, so both players see it. */
  readonly stack: readonly Card[];
  readonly battlefield: readonly Permanent[];
  readonly graveyard: readonly Card[];
  readonly exile: readonly Card[];
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
   * Null while the game is going.
   *
   * The app had no way to know a game had ended, so it carried on offering
   * plays to a player who had already lost — and the server accepted them.
   */
  readonly over: Over | null;
}
