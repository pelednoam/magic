/**
 * What tapping a card in hand actually sends.
 *
 * The rules distinction this app must not get wrong: playing a land (CR 305.1)
 * and casting a spell (CR 601) are different actions. This module decides
 * neither -- the server said which in `Playable` -- but it is where a wrong
 * answer would turn into a wrong board.
 *
 * The other thing it must not do is *resolve*. Tapping a card used to send a
 * cast and a resolution back to back, which closed the other player's window
 * to answer before it opened (CR 117.4). The tests that pinned the two events
 * together are gone, and the one that asserts there is only the cast is here
 * in their place -- because a test pinning the old shape would make the old
 * shape deliberate.
 */

import { describe, expect, it } from "vitest";

import { playing } from "../src/playing";

describe("what tapping a card in hand sends", () => {
  const land = {
    instance_id: "l1",
    name: "Forest",
    is_land: true,
    is_permanent: true,
    playable: true,
    reasons: [],
    not_carried_out: [],
    payment: null,
  };
  const bear = {
    ...land,
    instance_id: "b1",
    name: "Grizzly Bears",
    is_land: false,
    payment: { tap: ["l1", "l2"], keep: [] },
  };
  const opt = { ...bear, instance_id: "o1", name: "Opt", is_permanent: false };

  it("plays a land with the land drop, which is what spends it", () => {
    expect(playing(land, "you")).toEqual([
      { type: "play_land", player: "you", instance_id: "l1" },
    ]);
  });

  it("casts, carrying what pays for it, because CR 601.2 is one action", () => {
    // Announcing the spell and paying for it happen without stopping, and no
    // player receives priority part-way through. Sending the taps first also
    // meant the server rechecked affordability with the mana already spent, so
    // every paid cast came back "you need 2 more untapped sources".
    expect(playing(bear, "you")).toEqual([
      {
        type: "cast_spell",
        player: "you",
        instance_id: "b1",
        payment: ["l1", "l2"],
      },
    ]);
  });

  it("does not resolve the spell it just cast", () => {
    // The whole of R04 in one assertion. A cast followed immediately by a
    // resolution is the app deciding, for the other player, that they had
    // nothing to say -- and a spell resolves because every player passed in
    // succession (CR 117.4), which is two events this app must not send for
    // somebody else.
    for (const card of [bear, opt]) {
      const kinds = playing(card, "you").map((event) => event["type"]);
      expect(kinds).toEqual(["cast_spell"]);
      expect(kinds).not.toContain("resolve_spell");
      expect(kinds).not.toContain("pass_priority");
    }
  });

  it("casts a free spell with nothing tapped", () => {
    expect(playing({ ...opt, payment: null }, "you")[0]).toMatchObject({ payment: [] });
  });
});
