/**
 * What the stack panel says, worked out where it can be tested.
 *
 * A component cannot be imported by this suite -- `react-native`'s entry point
 * is Flow and rollup cannot parse it -- so the project's rule is that anything
 * worth testing in a component lives outside it. This is the outside for
 * `Priority`, and every line of it is worth testing: it is what a player reads
 * to decide whether they still have a say.
 *
 * It decides nothing about the rules and could not. Who may act, who has
 * passed and where a spell resolves to are fields the server sent; these
 * functions only choose the sentence and the order to show them in. The one
 * thing they are careful about is the difference between "nobody may act" and
 * "we do not know", which are opposite answers and used to look alike.
 */

import type { GameState, Waiting } from "./wire";

/**
 * The stack with the top first.
 *
 * The wire sends it bottom first, the way a stack is built -- each object goes
 * on top of everything already there (CR 405.2). A person reads downwards, and
 * the thing that happens next is the top one (CR 405.5), so it goes first.
 */
export function waiting(state: GameState): readonly Waiting[] {
  return [...state.stack].reverse();
}

/**
 * Whose moment this is, in one line.
 *
 * Every branch is a field the server sent. Nobody holding priority is not a
 * missing answer: it is the untap step, the cleanup step (CR 502.4, CR 514.3),
 * or the instant after everybody passed, when the top of the stack resolves or
 * the step ends (CR 117.4). Saying which beats a blank.
 */
export function whoseMove(state: GameState, seat: string): string {
  if (state.priority === seat) {
    return "Your move";
  }
  if (state.priority !== null) {
    return "Waiting for them";
  }
  if (state.stack.length > 0) {
    return "Both passed — the top spell resolves";
  }
  return "Nobody can act right now";
}

/** The spell about to resolve, and what resolving it would take. */
export interface Resolving {
  readonly card: Waiting;
  /** Whether this seat is the one that resolves it (CR 405.4). */
  readonly yours: boolean;
  /**
   * Where it goes -- `battlefield` (CR 608.3) or `graveyard` (CR 608.2m) --
   * or the empty string when the coach cannot identify the card and so cannot
   * say. Not a guess: `api.guard` refuses that resolution for the same
   * reason, so a button would only ever offer a refusal.
   */
  readonly to: string;
}

/**
 * The spell that resolves next, or undefined while somebody may still act.
 *
 * "Nobody holds priority" is exactly what "every player has passed" looks like
 * on the wire (CR 117.4), and it is read from the field rather than worked out
 * from the passes -- which of the two it means is the server's to decide, and
 * a client that recomputed it would be a second rules engine.
 */
export function resolving(state: GameState, seat: string): Resolving | undefined {
  const top = waiting(state)[0];
  if (state.priority !== null || top === undefined) {
    return undefined;
  }
  return { card: top, yours: top.controller === seat, to: top.resolves_to ?? "" };
}
