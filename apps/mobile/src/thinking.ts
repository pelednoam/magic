/**
 * The two slow asks, as hooks, because each has a rule about staleness.
 *
 * Both call Claude through the server and both take about a minute, which is
 * long enough for the board to change underneath them. What to do about that
 * differs, and the difference is the reason these are here rather than inline:
 *
 * - **Turn advice is about a position.** It is cleared the moment the board
 *   moves, and an answer that arrives after a change is dropped. Advice about a
 *   board nobody is looking at any more reads as current, which is worse than
 *   no advice at all.
 * - **A rules answer is about the rules** -- but it is asked *with the board in
 *   the prompt*, so "can my creature block that one?" is answered about the
 *   creatures that were there. Once they are not, the answer is about a
 *   position nobody is in, exactly like stale turn advice.
 *
 * So both behave the same way: cleared when the board moves, and an answer that
 * arrives after the board moved is dropped rather than displayed. Clearing
 * alone was not enough -- the panel went blank on the change and then a minute
 * later the old answer wrote itself back in, which is worse than either.
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

/** Turn advice, dropped whenever the board moves. */
export function useCoaching(
  coach: Coach,
  sessionId: string,
  seat: string,
  version: number,
): Thinking<Coaching> & { readonly ask: () => void } {
  const [reply, setReply] = useState<Coaching | null>(null);
  const [asking, setAsking] = useState(false);
  const [problem, setProblem] = useState("");

  // The version as the callback sees it when its promise resolves, which is not
  // the version it closed over: `ask` is made once per render and answers a
  // minute later.
  const current = useRef(version);
  useEffect(() => {
    current.current = version;
    setReply(null);
    setProblem("");
  }, [version]);

  const ask = useCallback(() => {
    setAsking(true);
    setProblem("");
    const asked = current.current;
    coach
      .explain(sessionId, seat)
      .then((answer: Coaching) => {
        if (asked === current.current) {
          setReply(answer);
        }
      })
      .catch((error: unknown) => {
        if (asked === current.current) {
          setProblem(messageOf(error));
        }
      })
      .finally(() => { setAsking(false); });
  }, [coach, seat, sessionId]);

  return { reply, asking, problem, ask };
}

/** Rules answers, which outlive the board they were asked over. */
export function useQuestions(
  coach: Coach,
  sessionId: string,
  seat: string,
  version: number,
): Thinking<Asked> & { readonly ask: (question: string) => void } {
  const [reply, setReply] = useState<Asked | null>(null);
  const [asking, setAsking] = useState(false);
  const [problem, setProblem] = useState("");

  const current = useRef(version);
  useEffect(() => {
    current.current = version;
    setReply(null);
    setProblem("");
  }, [version]);

  const ask = useCallback(
    (question: string) => {
      setAsking(true);
      setProblem("");
      const asked = current.current;
      coach
        .ask(sessionId, question, seat)
        .then((answer: Asked) => {
          if (asked === current.current) {
            setReply(answer);
          }
        })
        .catch((error: unknown) => {
          if (asked === current.current) {
            setProblem(messageOf(error));
          }
        })
        .finally(() => { setAsking(false); });
    },
    [coach, seat, sessionId],
  );

  return { reply, asking, problem, ask };
}
