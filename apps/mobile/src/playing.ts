/**
 * What tapping a card in hand actually sends.
 *
 * Playing a land and casting a spell are different actions in the rules
 * (CR 305.1 and CR 601), and they are different events here.
 *
 * A spell is *one* event, and it used to be two. Casting is paying: CR 601.2
 * runs from announcing the spell to paying its cost without stopping, and no
 * player receives priority part-way through. Sending the taps first was both
 * wrong about that and broken — the server rechecks affordability when the
 * cast arrives, and by then the mana it would have counted was already spent.
 *
 * **Resolving is not sent from here, and that is the fix this file exists
 * for.** It used to be the second half of this function: tap a card, and the
 * app cast it and resolved it in one gesture. A spell resolves because every
 * player has passed in succession (CR 117.4, CR 608.1), so a cast followed
 * immediately by a resolution closed the other player's only window to answer
 * before it opened — in the app whose whole purpose is to teach a nine-year-old
 * that the window is there. Passing and resolving are deliberate acts now, in
 * `Priority`, and the server refuses a resolution that has not been passed to.
 *
 * This decides nothing about the rules. Whether the card is a land and what
 * pays for it are answers the server computed and put in `Playable`; this only
 * spells them as events.
 */

import type { Playable } from "./wire";

/** The events that play one card, in the order they must be applied. */
export function playing(card: Playable, seat: string): readonly Record<string, unknown>[] {
  if (card.is_land) {
    return [{ type: "play_land", player: seat, instance_id: card.instance_id }];
  }
  return [
    {
      type: "cast_spell",
      player: seat,
      instance_id: card.instance_id,
      // The engine's own choice of which lands to tap, sent back unchanged.
      // The server checks that they cover the cost before tapping any of them.
      payment: card.payment?.tap ?? [],
    },
  ];
}
