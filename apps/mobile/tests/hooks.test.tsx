/**
 * The two hooks that decide whether an answer is still about this board.
 *
 * This is the client half of the M6 safety story and it had no tests at all.
 * What it gets wrong is not visible in a type check: an answer that arrives a
 * minute after the board moved is *correct* — about a position nobody is in —
 * and showing it is worse than showing nothing, because it reads as current.
 *
 * Rendered into a real DOM; see `hookharness.tsx` for how, and why that is as
 * close to the app as this suite can get.
 */

import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCoaching, useQuestions } from "../src/thinking";
import type { Asked, Coaching } from "../src/wire";

import { ADVICE, ASKED, deferred, mounted, roots } from "./hookharness";

beforeEach(() => {
  roots.length = 0;
});

afterEach(() => {
  act(() => { roots.forEach((root) => { root.unmount(); }); });
  vi.restoreAllMocks();
});

describe("turn advice", () => {
  it("shows an answer that arrives while the board has not moved", async () => {
    const { coach, settle } = deferred<Coaching>();
    const hook = mounted((version) => useCoaching(coach, "g1", "you", version));
    act(() => { hook.latest().ask(""); });
    expect(hook.latest().asking).toBe(true);
    await settle(ADVICE);
    expect(hook.latest().reply?.explanation.in_short).toBe("Play a land.");
    expect(hook.latest().asking).toBe(false);
  });

  it("drops an answer that arrives after the board moved", async () => {
    const { coach, settle } = deferred<Coaching>();
    const hook = mounted((version) => useCoaching(coach, "g1", "you", version));
    act(() => { hook.latest().ask(""); });
    hook.moveBoard();
    await settle(ADVICE);
    expect(hook.latest().reply).toBeNull();
  });

  it("clears an answer already on screen when the board moves", async () => {
    const { coach, settle } = deferred<Coaching>();
    const hook = mounted((version) => useCoaching(coach, "g1", "you", version));
    act(() => { hook.latest().ask(""); });
    await settle(ADVICE);
    hook.moveBoard();
    expect(hook.latest().reply).toBeNull();
  });

  it("keeps the server's sentence when there was no answer", async () => {
    const { coach, fail } = deferred<Coaching>();
    const hook = mounted((version) => useCoaching(coach, "g1", "you", version));
    act(() => { hook.latest().ask(""); });
    await fail(new Error("no claude"));
    expect(hook.latest().problem).toContain("no claude");
    expect(hook.latest().asking).toBe(false);
  });

  it("drops a failure that arrives after the board moved", async () => {
    const { coach, fail } = deferred<Coaching>();
    const hook = mounted((version) => useCoaching(coach, "g1", "you", version));
    act(() => { hook.latest().ask(""); });
    hook.moveBoard();
    await fail(new Error("no claude"));
    expect(hook.latest().problem).toBe("");
  });
});

describe("rules answers", () => {
  it("shows an answer that arrives while the board has not moved", async () => {
    const { coach, settle } = deferred<Asked>();
    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("how does trample work?"); });
    await settle(ASKED);
    expect(hook.latest().reply?.answer.in_short).toBe("It gets through.");
  });

  it("drops an answer that arrives after the board moved", async () => {
    // The question was asked with the board in the prompt, so an answer about
    // creatures that have gone is about a position nobody is in. Clearing on
    // the change was not enough on its own: the panel went blank and then the
    // old answer wrote itself back in a minute later.
    const { coach, settle } = deferred<Asked>();
    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("can my creature block that one?"); });
    hook.moveBoard();
    await settle(ASKED);
    expect(hook.latest().reply).toBeNull();
  });

  it("clears an answer already on screen when the board moves", async () => {
    const { coach, settle } = deferred<Asked>();
    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("q"); });
    await settle(ASKED);
    hook.moveBoard();
    expect(hook.latest().reply).toBeNull();
  });

  it("drops a failure that arrives after the board moved", async () => {
    const { coach, fail } = deferred<Asked>();
    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("q"); });
    hook.moveBoard();
    await fail(new Error("rules are not installed"));
    expect(hook.latest().problem).toBe("");
  });
});
