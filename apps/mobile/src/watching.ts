/**
 * Following a game over the socket, as a hook.
 *
 * Split out of `Game` at the length limit, and the seam is a real one: the
 * screen is about what a player sees and this is about a connection that can
 * drop. It is also the one piece of that screen with no rendering in it, which
 * is why it can be tested without one.
 *
 * The socket carries the *other* device's changes. Our own come back from the
 * request that caused them, so there is one path for each and neither has to
 * guess.
 */

import { useEffect, useState } from "react";

import type { Coach } from "./client";
import { isSnapshot } from "./wire";
import type { Snapshot } from "./wire";

/**
 * Watch one game, handing every update to `accept`.
 *
 * Returns whether updates are still arriving. A board that has stopped
 * updating must not keep looking live: the other device's plays would simply
 * stop appearing, with nothing on screen to say so.
 */
export function useWatching(
  coach: Coach,
  sessionId: string,
  accept: (update: Snapshot) => void,
): boolean {
  const [watching, setWatching] = useState(true);
  useEffect(() => {
    const socket = new WebSocket(coach.watchUrl(sessionId));
    socket.onopen = () => { setWatching(true); };
    socket.onmessage = (message: MessageEvent<string>) => {
      const update: unknown = parse(message.data);
      if (isSnapshot(update)) {
        accept(update);
        return;
      }
      // A frame we cannot read is a broken server, not a broken game. The
      // board on screen is still the last one the server confirmed, and saying
      // so beats crashing one render later inside `snapshot.state.players`.
      setWatching(false);
    };
    socket.onclose = () => { setWatching(false); };
    socket.onerror = () => { setWatching(false); };
    return () => { socket.close(); };
  }, [accept, coach, sessionId]);
  return watching;
}

/** JSON, or undefined. A frame that is not JSON is not an exception here. */
function parse(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}
