/**
 * The two slow asks, as hooks, because each has a rule about staleness.
 *
 * Both call Claude through the server and both take about a minute, which is
 * long enough for the board to change underneath them. Turn advice is about a
 * position; so, it turns out, is a rules answer, because the question is asked
 * with the battlefield in its prompt. "Can my creature block that one?"
 * answered about creatures that have since died is about a position nobody is
 * in, and it reads as current.
 *
 * So both behave the same way, and the rule has two halves — clearing alone
 * was not enough, because the panel went blank on the change and then the old
 * answer wrote itself back in a minute later:
 *
 * - The panel is cleared the moment the board moves.
 * - An answer is dropped unless the *server* says it is about the board on
 *   screen. Each reply carries the revision it was computed from, which is
 *   better than the client remembering the version it had when it asked: that
 *   was a guess about what the server was doing, and this is what it did.
 *
 * Each request also carries a token, so two questions in flight at once cannot
 * overwrite each other and the first to return cannot clear the spinner the
 * second is still using.
 */

import { useCallback, useRef, useState } from "react";

import type { Coach } from "./client";
import { messageOf } from "./errors";
import type { Asked, Coaching } from "./wire";

/** A slow ask in progress, or its result, or why there is neither. */
export interface Thinking<T> {
  readonly reply: T | null;
  readonly asking: boolean;
  /** The server's own sentence when there was no answer at all. */
  readonly problem: string;
}

/** What both hooks do, differing only in the call they make. */
function useSlowAsk<T extends { readonly version: number }, A extends unknown[]>(
  send: (...args: A) => Promise<T>,
  version: number,
  /**
   * Which board that version counts. A version is a number per *game*, so two
   * games are both on 0 to start with — and an answer about one of them would
   * have matched the other. Same for the two seats, which get different advice
   * about the same board.
   */
  board: string,
): Thinking<T> & { readonly ask: (...args: A) => void } {
  // One piece of state, not three. They only ever change together, and a
  // panel that showed an answer and a spinner at once was possible while they
  // did not.
  const [held, setHeld] = useState<Thinking<T>>(NOTHING as Thinking<T>);

  // The board as it is *now*, which is not what the callback closed over: it
  // is made once per render and answers a minute later.
  const current = useRef(version);
  const showing = useRef(board);
  // Which request the panel is showing. A second question started while the
  // first is in flight makes the first's reply irrelevant, including its
  // "finished" — otherwise the spinner stopped while the second was running.
  const token = useRef(0);

  // Read during render, not in an effect. Clearing in an effect meant one
  // committed render paired the new board with the previous answer — a frame
  // of advice about a position nobody is in, which is the whole thing this
  // exists to prevent. It also left the in-flight request holding the button
  // disabled for up to its full minute, over a result nothing could use.
  const moved = current.current !== version || showing.current !== board;
  if (moved) {
    current.current = version;
    showing.current = board;
    token.current += 1;
    if (held.reply !== null || held.problem !== "" || held.asking) {
      setHeld(NOTHING as Thinking<T>);
    }
  }
  // Returned rather than only scheduled. `setHeld` queues a re-render; this
  // render is still holding the old value, and returning it would put the
  // previous answer next to the new board for one committed frame — which is
  // the exact thing being prevented, briefly.
  const shown = moved ? (NOTHING as Thinking<T>) : held;

  const ask = useCallback(
    (...args: A) => {
      token.current += 1;
      const mine = token.current;
      const asked = current.current;
      // Still the request the panel is showing, and still about the board it
      // is showing. An error carries no revision of its own — there is no
      // reply — so it falls back to the board we knew about when we asked,
      // which is what a reply uses the server's answer instead of.
      const here = showing.current;
      const stillWanted = () =>
        mine === token.current && asked === current.current && here === showing.current;
      setHeld({ reply: null, problem: "", asking: true });
      send(...args)
        .then((answer: T) => {
          // The server's own answer to "which board is this about", compared
          // against the board on screen. Better than `asked`: that is what the
          // client believed when it asked, and this is what the server did.
          if (
            mine === token.current &&
            here === showing.current &&
            answer.version === current.current
          ) {
            setHeld({ reply: answer, problem: "", asking: false });
          }
        })
        .catch((error: unknown) => {
          if (stillWanted()) {
            setHeld({ reply: null, problem: messageOf(error), asking: false });
          }
        })
        .finally(() => {
          if (mine === token.current) {
            setHeld((shown) => (shown.asking ? { ...shown, asking: false } : shown));
          }
        });
    },
    [send],
  );

  return { ...shown, ask };
}

/** Nothing asked, nothing answered, nothing wrong. */
const NOTHING = { reply: null, problem: "", asking: false } as const;

/** Turn advice, dropped whenever the board moves. */
export function useCoaching(
  coach: Coach,
  sessionId: string,
  seat: string,
  version: number,
): Thinking<Coaching> & { readonly ask: () => void } {
  const send = useCallback(() => coach.explain(sessionId, seat), [coach, seat, sessionId]);
  return useSlowAsk<Coaching, []>(send, version, `${sessionId}/${seat}`);
}

/** Rules answers, which go stale the same way: the board is in the prompt. */
export function useQuestions(
  coach: Coach,
  sessionId: string,
  seat: string,
  version: number,
): Thinking<Asked> & { readonly ask: (question: string) => void } {
  const send = useCallback(
    (question: string) => coach.ask(sessionId, question, seat),
    [coach, seat, sessionId],
  );
  return useSlowAsk<Asked, [string]>(send, version, `${sessionId}/${seat}`);
}

/**
 * A token for "is this reply still the one being waited for".
 *
 * Every call returns a predicate that stays true until the next call. A screen
 * takes one before each slow request and drops the reply if it is false by the
 * time it arrives.
 *
 * The same rule the two hooks above apply to a board that moved, in the shape
 * a screen with several slow calls needs: choosing a game and then going back
 * left a fetch in flight that put the screen back where it had just left, a
 * second after leaving. Calling this with no request to follow is the way to
 * say "whatever is in flight, I no longer want it".
 */
export function useLatest(): () => () => boolean {
  const wanted = useRef(0);
  return useCallback(() => {
    wanted.current += 1;
    const mine = wanted.current;
    return () => mine === wanted.current;
  }, []);
}
