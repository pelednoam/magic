/**
 * What tapping a card in hand actually sends.
 *
 * Playing a land and casting a spell are different actions in the rules
 * (CR 305.1 and CR 601), and they are different events here. A spell is three
 * of them: tap what pays for it, put it on the stack, let it resolve.
 *
 * This decides nothing about the rules. Whether the card is a land, what its
 * payment is, and whether it leaves a permanent behind are all answers the
 * server already computed and put in `Playable`; this only spells them as
 * events. Sent one at a time, and each is legal on its own, so the game's log
 * is a record of what happened rather than a summary of it — which is what a
 * replay is rebuilt from.
 */

import type { Playable } from "./wire";

/** The events that play one card, in the order they must be applied. */
export function playing(card: Playable, seat: string): readonly Record<string, unknown>[] {
  if (card.is_land) {
    return [{ type: "play_land", player: seat, instance_id: card.instance_id }];
  }
  const paying = (card.payment?.tap ?? []).map((source) => ({
    type: "set_tapped",
    player: seat,
    instance_id: source,
    tapped: true,
  }));
  return [
    ...paying,
    { type: "cast_spell", player: seat, instance_id: card.instance_id },
    {
      type: "resolve_spell",
      player: seat,
      instance_id: card.instance_id,
      // CR 608.3 and CR 608.2m: a permanent spell becomes a permanent, and an
      // instant or sorcery goes to its owner's graveyard. The server read the
      // type line and said which; this app does not know and must not guess.
      to: card.is_permanent ? "battlefield" : "graveyard",
    },
  ];
}
