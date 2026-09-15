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

/**
 * Which engine, card data and rules a board was produced under.
 *
 * Every field is empty when nothing recorded it — which is what a journal
 * written before any of this existed reads back as. Empty means "not
 * recorded", never "none": an old game is missing this, not wrong about it.
 *
 * Diagnostic, not a gate. The engine itself refuses an event it no longer
 * considers legal and the server then declines to show that game; these three
 * are what turn "this will not open" into "this was made by a different
 * engine".
 */
export interface Sources {
  /** A digest over the rules engine's source. */
  readonly engine: string;
  /** The checksum of the sealed card-data fixture. */
  readonly cards: string;
  /** The date the Comprehensive Rules say they took effect. */
  readonly rules: string;
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
  /**
   * The cards in this hand, or **null** when it is not this device's hand.
   *
   * A hand is a hidden zone (CR 400.2). The server used to send both to both
   * devices and "you cannot see your opponent's hand" held because nobody
   * looked; each device has its own token now and is sent one hand — see
   * `Snapshot.seat`.
   *
   * Null, not an empty list: an empty list says this player is holding
   * nothing, which is a different fact about the game and one a player would
   * act on.
   */
  readonly hand: readonly Card[] | null;
  /**
   * How many cards this player is holding, always.
   *
   * Public information — CR 400.2 hides the *contents* of a hand, not the
   * number — and the thing a player at a table actually counts. So hiding the
   * other list costs this tracker nothing it should have had.
   */
  readonly hand_size: number;
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
