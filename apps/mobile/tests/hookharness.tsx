/**
 * Rendering a hook into a real DOM, so its staleness rules can be exercised.
 *
 * As close as this suite can get to the app: importing a component would pull
 * in `react-native`, whose entry point is Flow and which rollup cannot parse.
 * That is also why anything worth testing in a component lives in `format.ts`
 * or `thinking.ts` rather than inside the component.
 */

import { act, useState } from "react";
import { createRoot } from "react-dom/client";

import type { Coach } from "../src/client";
import type { Asked, Coaching } from "../src/wire";

export const ADVICE = {
  explanation: {
    play: "land-1",
    attack: [],
    because: "A land is free.",
    in_short: "Play a land.",
    watch_out: [],
    check_yourself: [],
  },
  trusted: true,
  version: 0,
} satisfies Coaching;

const ANSWER = {
  answer: "Lethal first, then the rest.",
  in_short: "It gets through.",
  citations: ["702.19b"],
  unsure: "",
} satisfies Asked["answer"];

export const ASKED = { answer: ANSWER, cited: true, rules: [], version: 0 } satisfies Asked;

/** A `Coach` whose one slow call the test resolves by hand. */
export function deferred<T>(): {
  readonly coach: Coach;
  /** The same promise the stand-in returns, for a test wiring two of them. */
  readonly pending: Promise<T>;
  readonly settle: (value: T) => Promise<void>;
  readonly fail: (error: Error) => Promise<void>;
} {
  let resolve: (value: T) => void = () => undefined;
  let reject: (error: Error) => void = () => undefined;
  const pending = new Promise<T>((ok, no) => {
    resolve = ok;
    reject = no;
  });
  const coach = {
    explain: () => pending,
    ask: () => pending,
  } as unknown as Coach;
  return {
    coach,
    pending,
    settle: async (value: T) => {
      await act(async () => {
        resolve(value);
        await pending;
      });
    },
    fail: async (error: Error) => {
      await act(async () => {
        reject(error);
        await pending.catch(() => undefined);
      });
    },
  };
}

type Hook<T> = { reply: T | null; asking: boolean; problem: string };

/** Whatever arguments this hook's `ask` takes: none, or a question. */
type Asks<A extends unknown[]> = { readonly ask: (...args: A) => void };

/** Render a hook, and let the test change the board version under it. */
export function mounted<T, A extends unknown[]>(
  use: (version: number) => Hook<T> & Asks<A>,
): {
  readonly latest: () => Hook<T> & Asks<A>;
  readonly moveBoard: () => void;
  /** Render again without changing the version, for a test that changed
   *  something the hook closes over rather than something it is passed. */
  readonly rerender: () => void;
} {
  let seen: (Hook<T> & Asks<A>) | null = null;
  let setVersion: (n: number) => void = () => undefined;
  let setNudge: (next: (n: number) => number) => void = () => undefined;

  function Probe() {
    const [version, set] = useState(0);
    const [nudge, bump] = useState(0);
    setVersion = set;
    setNudge = bump;
    void nudge;
    seen = use(version);
    return null;
  }

  const host = document.createElement("div");
  const root = createRoot(host);
  act(() => { root.render(<Probe />); });
  roots.push(root);
  return {
    latest: () => {
      if (seen === null) {
        throw new Error("the hook never rendered");
      }
      return seen;
    },
    moveBoard: () => {
      act(() => {
        setVersion(Math.random());
      });
    },
    rerender: () => {
      act(() => {
        setNudge((n) => n + 1);
      });
    },
  };
}


/** Every root a test mounted, so the suite can unmount them afterwards. */
export const roots: { unmount: () => void }[] = [];


/**
 * Let every pending promise settle, inside `act`.
 *
 * A `finally` from an earlier request lands one microtask after the thing that
 * triggered it, so without this React warns that a state update happened
 * outside `act` -- and a gate that prints warnings on a green run teaches
 * everyone to ignore it.
 */
export async function settled(): Promise<void> {
  await act(async () => {
    await Promise.resolve();
  });
}
