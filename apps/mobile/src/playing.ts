/**
 * What tapping a card in hand actually sends.
 *
 * Playing a land and casting a spell are different actions in the rules
 * (CR 305.1 and CR 601), and they are different events here.
 *
 * A spell is two events, not three. Casting *is* paying: CR 601.2 runs from
 * announcing the spell to paying its cost without stopping, and no player
 * receives priority part-way through. Sending the taps first was both wrong
 * about that and broken — the server rechecks affordability when the cast
 * arrives, and by then the mana it would have counted was already spent, so
 * every paid cast was refused. The gap that is left, between casting and
 * resolving, is the real one: it is where answering a spell will go.
 *
 * This decides nothing about the rules. Whether the card is a land, what pays
 * for it, and whether it leaves a permanent behind are all answers the server
 * computed and put in `Playable`; this only spells them as events.
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
