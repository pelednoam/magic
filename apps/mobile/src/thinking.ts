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

import { useCallback, useEffect, useRef, useState } from "react";

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
): Thinking<T> & { readonly ask: (...args: A) => void } {
  const [reply, setReply] = useState<T | null>(null);
  const [asking, setAsking] = useState(false);
  const [problem, setProblem] = useState("");

  // The board as it is *now*, which is not what the callback closed over: it
  // is made once per render and answers a minute later.
  const current = useRef(version);
  // Which request the panel is showing. A second question started while the
  // first is in flight makes the first's reply irrelevant, including its
  // "finished" — otherwise the spinner stopped while the second was running.
  const token = useRef(0);

  useEffect(() => {
    current.current = version;
    setReply(null);
    setProblem("");
  }, [version]);

  const ask = useCallback(
    (...args: A) => {
      token.current += 1;
      const mine = token.current;
      const asked = current.current;
      // Still the request the panel is showing, and still about the board it
      // is showing. An error carries no revision of its own -- there is no
      // reply -- so it falls back to the board we knew about when we asked,
      // which is what a reply uses the server's answer instead of.
      const stillWanted = () => mine === token.current && asked === current.current;
      setAsking(true);
      setProblem("");
      setReply(null);
      send(...args)
        .then((answer: T) => {
          // The server's own answer to "which board is this about", compared
          // against the board on screen. Better than `asked`: that is what the
          // client believed when it asked, and this is what the server did.
          if (mine === token.current && answer.version === current.current) {
            setReply(answer);
          }
        })
        .catch((error: unknown) => {
          if (stillWanted()) {
            setProblem(messageOf(error));
          }
        })
        .finally(() => {
          if (mine === token.current) {
            setAsking(false);
          }
        });
    },
    [send],
  );

  return { reply, asking, problem, ask };
}

/** Turn advice, dropped whenever the board moves. */
export function useCoaching(
  coach: Coach,
  sessionId: string,
  seat: string,
  version: number,
): Thinking<Coaching> & { readonly ask: () => void } {
  const send = useCallback(
    () => coach.explain(sessionId, seat),
    [coach, seat, sessionId],
  );
  return useSlowAsk<Coaching, []>(send, version);
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
  return useSlowAsk<Asked, [string]>(send, version);
}
