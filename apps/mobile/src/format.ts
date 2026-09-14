/**
 * Turning what the server said into what goes on screen.
 *
 * The only module here with any logic in it, and it is all presentation: how to
 * spell a step, how to name a card by its identifier, how to put a list into a
 * sentence. Nothing decides anything about the game -- every judgement arrived
 * already made, in `reasons`, `playable` and `unavailable`.
 *
 * The test for whether something belongs here: could it ever disagree with the
 * engine? If yes, it belongs in Python.
 */

import type { Card, Permanent, Plan, Player } from "./wire";

/** `precombat_main` as a person says it. */
export function stepName(step: string): string {
  const words = step.split("_").join(" ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** "Turn 3 — Precombat main", or whose turn it is when it is not yours. */
export function turnLine(turn: number, step: string, yourTurn: boolean): string {
  return `Turn ${turn} · ${stepName(step)}${yourTurn ? "" : " · their turn"}`;
}

/** The name printed on a card, found by the identifier the advice used. */
export function nameOf(board: Player, instanceId: string): string {
  const everywhere: readonly Card[] = [...board.battlefield, ...board.hand];
  return everywhere.find((card) => card.instance_id === instanceId)?.name ?? instanceId;
}

/** Several names, as a person would say them: "a, b and c". */
export function listed(names: readonly string[]): string {
  if (names.length === 0) {
    return "";
  }
  if (names.length === 1) {
    return names[0] ?? "";
  }
  return `${names.slice(0, -1).join(", ")} and ${names[names.length - 1] ?? ""}`;
}

/** "Tap Forest and Forest, keep Island up." */
export function paymentLine(
  board: Player,
  tap: readonly string[],
  keep: readonly string[],
): string {
  const tapped = listed(tap.map((id) => nameOf(board, id)));
  if (keep.length === 0) {
    return `Tap ${tapped}`;
  }
  return `Tap ${tapped} · keep ${listed(keep.map((id) => nameOf(board, id)))} up`;
}

/** What an attack does, in one line, with the maths shown. */
export function planLine(plan: Plan): string {
  const parts = [`${plan.damage} damage`];
  if (plan.lethal) {
    parts.push("LETHAL");
  } else {
    parts.push(`they go to ${plan.defender_life_after}`);
  }
  if (plan.they_lose.length > 0) {
    parts.push(`kills ${listed(plan.they_lose)}`);
  }
  if (plan.you_lose.length > 0) {
    parts.push(`loses ${listed(plan.you_lose)}`);
  }
  if (plan.you_gain > 0) {
    parts.push(`+${plan.you_gain} life`);
  }
  return parts.join(" · ");
}

/** How to describe an attack that is really "do not attack". */
export function planTitle(plan: Plan): string {
  return plan.attackers.length === 0 ? "Hold back" : listed(plan.attackers);
}

/** The two states a permanent can be in that stop it doing things. */
export function permanentNote(permanent: Permanent): string {
  const notes: string[] = [];
  if (permanent.tapped) {
    notes.push("tapped");
  }
  if (permanent.summoning_sick) {
    notes.push("just arrived");
  }
  return notes.join(" · ");
}

/**
 * The plan whose attackers are exactly these, or undefined.
 *
 * The server already established that one exists before it passed the coach's
 * answer on; this finds it again so the screen prints the engine's names and
 * the engine's numbers rather than anything the model wrote. Compared as a set,
 * because the order a model lists creatures in means nothing.
 */
export function planFor(
  plans: readonly Plan[],
  wanted: readonly string[],
): Plan | undefined {
  if (wanted.length === 0) {
    return undefined;
  }
  const sought = key(wanted);
  return plans.find((plan) => key(plan.attacker_ids) === sought);
}

/** A set of identifiers, as one comparable string. */
function key(ids: readonly string[]): string {
  return [...ids].sort().join("|");
}
