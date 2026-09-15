/**
 * What tapping a card in hand actually sends.
 *
 * The rules distinction this app must not get wrong: playing a land (CR 305.1)
 * and casting a spell (CR 601) are different actions, and a spell that resolves
 * goes to the battlefield or to its owner's graveyard depending on its type
 * (CR 608.3, CR 608.2m). This module decides none of that -- the server read
 * the type line and put the answer in `Playable` -- but it is where a wrong
 * answer would turn into a wrong board.
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

  it("taps what pays, then casts, then resolves", () => {
    expect(playing(bear, "you").map((event) => event["type"])).toEqual([
      "set_tapped",
      "set_tapped",
      "cast_spell",
      "resolve_spell",
    ]);
  });

  it("sends a permanent spell to the battlefield (CR 608.3)", () => {
    expect(playing(bear, "you").at(-1)).toMatchObject({
      type: "resolve_spell",
      to: "battlefield",
    });
  });

  it("sends an instant to the graveyard (CR 608.2m)", () => {
    // The bug the whole event pair exists to fix: an Opt used to be moved to
    // the battlefield, where it sat for the rest of the game.
    expect(playing(opt, "you").at(-1)).toMatchObject({
      type: "resolve_spell",
      to: "graveyard",
    });
  });

  it("casts a free spell with nothing tapped", () => {
    expect(playing({ ...opt, payment: null }, "you")).toHaveLength(2);
  });
});
