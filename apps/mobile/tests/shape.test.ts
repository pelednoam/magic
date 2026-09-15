/**
 * Whether what came back off the wire is a snapshot at all.
 *
 * Split from `format.test.ts` at the length limit, and the seam is the
 * subject: that file is about words a person reads, this one is about a claim.
 * `JSON.parse(...) as Snapshot` accepted `null` and any object without
 * `state`, and the crash then arrived one render later inside
 * `snapshot.state.players[YOU]` — far from the frame that caused it, which is
 * the worst place for a type error to surface.
 */

import { describe, expect, it } from "vitest";

import { isSnapshot } from "../src/wire";

describe("a response is not a snapshot because we said so", () => {
  const good = {
    version: 0,
    rules_available: true,
    seat: "you",
    sources: { engine: "e1", cards: "c1", rules: "August 7, 2026" },
    state: { players: { you: {}, them: {} } },
    // One seat's advice, the one the payload says it is for. It used to carry
    // both, which was the other player's hand on this device.
    advice: { you: {} },
  };

  it("accepts the real shape", () => {
    expect(isSnapshot(good)).toBe(true);
  });

  it("rejects null, which a cast used to let through", () => {
    expect(isSnapshot(null)).toBe(false);
  });

  it("rejects a string", () => {
    expect(isSnapshot("ok")).toBe(false);
  });

  it("rejects an array, which is an object to `typeof`", () => {
    expect(isSnapshot([])).toBe(false);
  });

  it("rejects a snapshot with no version, because ordering depends on it", () => {
    expect(isSnapshot({ ...good, version: undefined })).toBe(false);
  });

  it("rejects a snapshot that does not say whether rules questions work", () => {
    // A server too old to send it would otherwise render the question box as
    // though it worked, which is the thing the flag exists to prevent.
    expect(isSnapshot({ ...good, rules_available: undefined })).toBe(false);
  });

  it("rejects a board with no players, which is what the screen reads", () => {
    expect(isSnapshot({ ...good, state: {} })).toBe(false);
  });

  it("rejects a board missing a seat", () => {
    expect(isSnapshot({ ...good, state: { players: { you: {} } } })).toBe(false);
  });

  it("rejects a payload that does not say which seat it is for", () => {
    // Without it the screen cannot tell which hand is its own.
    expect(isSnapshot({ ...good, seat: undefined })).toBe(false);
  });

  it("rejects advice for a seat other than the one it names", () => {
    expect(isSnapshot({ ...good, advice: { them: {} } })).toBe(false);
  });

  it("rejects a seat that is only an inherited property", () => {
    // `advice["__proto__"]` is `Object.prototype` -- an object, so a plain
    // lookup accepted it and the crash arrived later in `turnLine` with an
    // undefined step. A decoded payload's own keys are the only ones that
    // count, which is what `Object.hasOwn` is there for.
    expect(isSnapshot({ ...good, seat: "__proto__", advice: {} })).toBe(false);
  });

  it("rejects players that is an array", () => {
    expect(isSnapshot({ ...good, state: { players: [] } })).toBe(false);
  });
});
