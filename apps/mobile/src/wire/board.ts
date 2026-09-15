/**
 * What the engine computed about a position, written out to match
 * `services/api/views.py`.
 *
 * Hand-written, like the Python side it mirrors, and for the same reason: the
 * wire is a contract two people agreed on, not a dump of either side's types.
 * `tests/api/test_wire_contract.py` reads every file in this folder and fails
 * if the server starts sending a field none of them knows about, which is the
 * drift that would otherwise be found by a blank space in the UI.
 *
 * Nothing here interprets anything. `reasons` are sentences the engine wrote
 * and this app prints; it does not know what a land is, and must not learn.
 */


/** One card in hand, and the engine's verdict on it. */
export interface Playable {
  readonly instance_id: string;
  readonly name: string;
  /**
   * Whether playing this is a land drop. Playing a land (CR 305.1) and casting
   * a spell (CR 601) are different actions with different events, so a client
   * has to know which it is looking at.
   */
  readonly is_land: boolean;
  /**
   * Whether casting this leaves a permanent on the battlefield (CR 608.3) or
   * puts the card in its owner's graveyard as it resolves (CR 608.2m).
   *
   * The client sends it back in `resolve_spell`, because the engine holds no
   * card data and cannot work it out. This app still decides nothing: the
   * server read the type line and this carries the answer.
   */
  readonly is_permanent: boolean;
  readonly playable: boolean;
  /** Empty when playable. Otherwise the engine's own words, printed verbatim. */
  readonly reasons: readonly string[];
  /**
   * What the tracker will not do if you play this. Empty when it will do all
   * of it.
   *
   * A different thing from `reasons`, which is why you *cannot* play the card.
   * You can cast Giant Growth; the tracker simply will not change anybody's
   * toughness when you do, and every number it shows afterwards is computed
   * from a board that is wrong by three points. It used to come back playable
   * with nothing said, because the card's effect is *described* in the
   * fixture and being described is not being carried out.
   */
  readonly not_carried_out: readonly string[];
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
  /**
   * What the *rules engine* does not model at this moment, in its own words.
   *
   * The same admission `unknown` makes about cards, made about the rules. A
   * stack that holds only spells looks complete, and a child who learned from
   * it that a trigger cannot be answered would have learned something that is
   * not a rule of Magic. Shown, never hidden, for the same reason.
   */
  readonly not_modelled: readonly string[];
}
