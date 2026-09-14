/**
 * The tracker. One screen, one turn at a time.
 *
 * Every action is an *event* sent to the server, which decides what it means
 * and sends the whole board back (§4). Nothing is applied optimistically: the
 * server is the game, and a tracker that guessed ahead of it would be a second
 * rules engine written in the language chosen for not having one.
 */

import { useCallback, useEffect, useState } from "react";
import { ScrollView, StyleSheet, Text } from "react-native";

import { Attacks } from "../components/Attacks";
import { Board } from "../components/Board";
import { Coaching } from "../components/Coaching";
import { Controls } from "../components/Controls";
import { Hand } from "../components/Hand";
import { Question } from "../components/Question";
import { Reminders, Unknown } from "../components/Reminders";
import type { Coach } from "../client";
import { turnLine } from "../format";
import { useCoaching, useQuestions } from "../thinking";
import { colour, space, text } from "../theme";
import type { NewGame, Permanent, Playable, Snapshot } from "../wire";
import { isSnapshot } from "../wire";
import { THEM, YOU } from "../wire";

import { messageOf } from "./Start";

export function Game({
  coach,
  game,
  seat,
}: {
  readonly coach: Coach;
  readonly game: NewGame;
  /** Which side of the table this device is. Both are real seats; the app
   *  used to assume it was always "you", so a second device could only ever
   *  start its own game and neither could act as the other player. */
  readonly seat: string;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot>(game);
  const [problem, setProblem] = useState("");

  /**
   * Take a snapshot only if it is not older than the one on screen.
   *
   * Both an HTTP reply and a socket broadcast call this, and they race. Without
   * the check a reply that overtook a newer one rolled the board back
   * permanently -- an undo would appear to un-happen, and the next event would
   * be sent against a board the server had already moved past.
   */
  const accept = useCallback((update: Snapshot) => {
    setSnapshot((shown) => (update.version >= shown.version ? update : shown));
  }, []);

  // The socket is the other device's changes arriving. Our own come back from
  // the request that caused them, so there is one path for each and neither
  // has to guess.
  const [watching, setWatching] = useState(true);
  useEffect(() => {
    const socket = new WebSocket(coach.watchUrl(game.session_id));
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
    // A board that has stopped updating must not keep looking live: the other
    // device's plays would simply stop appearing, with nothing to say so.
    socket.onclose = () => { setWatching(false); };
    socket.onerror = () => { setWatching(false); };
    return () => { socket.close(); };
  }, [accept, coach, game.session_id]);

  const coaching = useCoaching(coach, game.session_id, seat, snapshot.version);
  const questions = useQuestions(coach, game.session_id, seat, snapshot.version);

  const act = useCallback(
    async (event: Record<string, unknown>): Promise<void> => {
      setProblem("");
      try {
        accept(await coach.event(game.session_id, event));
      } catch (error: unknown) {
        setProblem(messageOf(error));
      }
    },
    [accept, coach, game.session_id],
  );

  const other = seat === YOU ? THEM : YOU;
  const mine = snapshot.state.players[seat];
  const theirs = snapshot.state.players[other];
  const advice = snapshot.advice[seat];
  if (mine === undefined || theirs === undefined || advice === undefined) {
    return <Text style={styles.problem}>This game is not one this app can show.</Text>;
  }

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.turn}>
        {turnLine(advice.turn, advice.step, advice.your_turn)}
      </Text>
      {problem === "" ? null : <Text style={styles.problem}>{problem}</Text>}
      {watching ? null : (
        <Text style={styles.stale}>
          Not receiving updates — the other device&apos;s plays will not appear.
        </Text>
      )}

      <Reminders reminders={advice.reminders} />
      <Hand
        cards={advice.hand}
        board={mine}
        onPlay={(card: Playable) => {
          void act({ type: "play_land", player: seat, instance_id: card.instance_id });
        }}
      />
      <Attacks attacks={advice.attacks} />
      <Coaching
        reply={coaching.reply}
        asking={coaching.asking}
        problem={coaching.problem}
        hand={advice.hand}
        plans={advice.attacks.plans}
        onAsk={coaching.ask}
      />
      <Board
        title="Your battlefield"
        player={mine}
        onTap={(permanent: Permanent) => {
          void act({
            type: "set_tapped",
            player: seat,
            instance_id: permanent.instance_id,
            tapped: !permanent.tapped,
          });
        }}
      />
      <Board title="Their battlefield" player={theirs} />
      <Unknown cards={advice.unknown} />
      <Question
        reply={questions.reply}
        asking={questions.asking}
        problem={questions.problem}
        available={snapshot.rules_available}
        onAsk={questions.ask}
      />

      <Controls
        onStep={() => { void act({ type: "advance_step" }); }}
        onDraw={() => { void act({ type: "draw_card", player: seat }); }}
        onUndo={() => {
          setProblem("");
          coach
            .undo(game.session_id)
            .then(accept)
            .catch((error: unknown) => { setProblem(messageOf(error)); });
        }}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.medium, paddingBottom: space.large * 3 },
  turn: {
    color: colour.text,
    fontSize: text.title,
    fontWeight: "700",
    marginBottom: space.medium,
  },
  problem: { color: colour.no, fontSize: text.body, marginBottom: space.medium },
  stale: { color: colour.warn, fontSize: text.small, marginBottom: space.medium },
});

/** JSON, or undefined. A frame that is not JSON is not an exception here. */
function parse(text: string): unknown {
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return undefined;
  }
}
