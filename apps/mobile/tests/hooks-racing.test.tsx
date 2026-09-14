/**
 * Two slow asks racing, and a board that moves while one is in flight.
 *
 * All of these are about a request whose answer has stopped being the one the
 * panel wants: superseded by a newer question, or about a board nobody is on.
 * The failure is always the same shape -- something correct, shown as though
 * it were current.
 */

import { act } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useCoaching, useQuestions } from "../src/thinking";
import type { Asked, Coaching } from "../src/wire";

import { ADVICE, ASKED, deferred, mounted, roots, settled } from "./hookharness";

beforeEach(() => {
  roots.length = 0;
});

afterEach(() => {
  act(() => {
    roots.forEach((root) => {
      root.unmount();
    });
  });
  vi.restoreAllMocks();
});

describe("two questions at once", () => {
  it("does not let the first answer land in the second's panel", async () => {
    // Two in flight, and the first to return is not the one being shown.
    const first = deferred<Asked>();
    const second = deferred<Asked>();
    let which = 0;
    const coach = {
      ask: () => {
        which += 1;
        return which === 1 ? first.pending : second.pending;
      },
    } as unknown as Parameters<typeof useQuestions>[0];

    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("first question"); });
    act(() => { hook.latest().ask("second question"); });

    await first.settle({ ...ASKED, answer: { ...ASKED.answer, in_short: "first" } });
    expect(hook.latest().reply).toBeNull();
    expect(hook.latest().asking).toBe(true);

    await second.settle({ ...ASKED, answer: { ...ASKED.answer, in_short: "second" } });
    expect(hook.latest().reply?.answer.in_short).toBe("second");
    expect(hook.latest().asking).toBe(false);
  });

  it("clears the old answer while the new question is running", async () => {
    // Leaving it up would show an answer to the previous question next to a
    // spinner for this one, which reads as an answer to this one.
    const first = deferred<Asked>();
    const second = deferred<Asked>();
    let which = 0;
    const coach = {
      ask: () => {
        which += 1;
        return which === 1 ? first.pending : second.pending;
      },
    } as unknown as Parameters<typeof useQuestions>[0];

    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("first"); });
    await first.settle(ASKED);
    expect(hook.latest().reply).not.toBeNull();

    act(() => { hook.latest().ask("second"); });
    await settled();
    expect(hook.latest().reply).toBeNull();
    expect(hook.latest().asking).toBe(true);
  });
});

describe("an answer about a board nobody is on", () => {
  it("is dropped even when the client did not notice the move", async () => {
    // The server says which revision it answered about. That is the check --
    // not the version the client happened to remember when it asked.
    const { coach, settle } = deferred<Asked>();
    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("q"); });
    await settle({ ...ASKED, version: 99 });
    expect(hook.latest().reply).toBeNull();
  });
});

describe("a board that moves while a question is in flight", () => {
  it("frees the button instead of holding it for the whole timeout", () => {
    // The request's answer can no longer be used, so keeping the spinner up
    // meant the player could not ask about the board they were now on until
    // the old request had finished being irrelevant.
    const { coach } = deferred<Asked>();
    const hook = mounted((version) => useQuestions(coach, "g1", "you", version));
    act(() => { hook.latest().ask("q"); });
    expect(hook.latest().asking).toBe(true);
    hook.moveBoard();
    expect(hook.latest().asking).toBe(false);
  });

  it("never pairs the new board with the previous answer", async () => {
    // Clearing in an effect left one committed render showing both.
    const { coach, settle } = deferred<Coaching>();
    const seen: (Coaching | null)[] = [];
    const hook = mounted((version) => {
      const state = useCoaching(coach, "g1", "you", version);
      seen.push(state.reply);
      return state;
    });
    act(() => { hook.latest().ask(); });
    await settle(ADVICE);
    expect(seen.at(-1)).not.toBeNull();

    const before = seen.length;
    hook.moveBoard();
    const after = seen.slice(before);
    expect(after.length).toBeGreaterThan(0);
    expect(after).toEqual(after.map(() => null));
  });
});
