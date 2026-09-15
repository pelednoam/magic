/**
 * The tracker. One screen, one turn at a time.
 *
 * Every action is an *event* sent to the server, which decides what it means
 * and sends the whole board back (§4). Nothing is applied optimistically: the
 * server is the game, and a tracker that guessed ahead of it would be a second
 * rules engine written in the language chosen for not having one.
 */

import { useCallback, useState } from "react";
import { ScrollView, StyleSheet, Text } from "react-native";

import { Attacks } from "../components/Attacks";
import { Battlefields } from "../components/Battlefields";
import { Coaching } from "../components/Coaching";
import { Controls } from "../components/Controls";
import { Finished } from "../components/Finished";
import { Hand } from "../components/Hand";
import { Priority } from "../components/Priority";
import { Question } from "../components/Question";
import { Reminders, Unknown } from "../components/Reminders";
import type { Coach } from "../client";
import { messageOf } from "../errors";
import { turnLine } from "../format";
import { playing } from "../playing";
import { useCoaching, useQuestions } from "../thinking";
import { colour, space, text } from "../theme";
import { useWatching } from "../watching";
import type { NewGame, Playable, Snapshot } from "../wire";
import { THEM, YOU } from "../wire";


export function Game({
  coach,
  game,
}: {
  readonly coach: Coach;
  readonly game: NewGame;
}) {
  const [snapshot, setSnapshot] = useState<Snapshot>(game);
  const [problem, setProblem] = useState("");
  // Which side of the table this device is: the server's answer, read off the
  // token this app's requests carry. It used to be a prop chosen by which
  // button was pressed on the start screen, and a device set to the wrong seat
  // was a device acting as the other player.
  const seat = snapshot.seat;

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

  const watching = useWatching(coach, game.session_id, accept);

  const coaching = useCoaching(coach, game.session_id, seat, snapshot.version);
  const questions = useQuestions(coach, game.session_id, seat, snapshot.version);

  const act = useCallback(
    async (...events: readonly Record<string, unknown>[]): Promise<void> => {
      setProblem("");
      try {
        // In order, and one at a time: a later event depends on the earlier
        // one having been accepted. A refusal stops the rest, leaving the game
        // where the server last agreed it was.
        for (const event of events) {
          accept(await coach.event(game.session_id, event));
        }
      } catch (error: unknown) {
        setProblem(messageOf(error));
      }
    },
    [accept, coach, game.session_id],
  );

  // Whether anything can still be done. A finished game refuses every event,
  // so offering a tap would show the engine's refusal for no visible reason.
  const playable = snapshot.state.over === null;
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

      {snapshot.state.over === null ? null : (
        <Finished over={snapshot.state.over} seat={seat} />
      )}

      <Reminders reminders={advice.reminders} />
      <Hand
        cards={advice.hand}
        board={mine}
        // A finished game offers nothing. The server refuses every event in
        // one, so without this the only feedback for tapping a card would be
        // the engine's refusal text appearing for no reason a player can see.
        onPlay={playable ? (card: Playable) => { void act(...playing(card, seat)); } : undefined}
      />
      <Priority
        state={snapshot.state}
        seat={seat}
        // What the rules engine does not model at this moment, in its own
        // words. Beside the stack because that is what it is about: a stack
        // holding only spells looks complete, and a child who learned from it
        // that a trigger cannot be answered would have learned a wrong rule.
        gaps={advice.not_modelled}
        onPass={playable ? () => { void act({ type: "pass_priority", player: seat }); } : undefined}
        onResolve={
          playable
            ? (instanceId: string, to: string) => {
                // Where it resolves to is the server's answer, sent back
                // unchanged: it read the type line (CR 608.3, CR 608.2m) and
                // this app does not know how and must not guess.
                void act({ type: "resolve_spell", player: seat, instance_id: instanceId, to });
              }
            : undefined
        }
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
      <Battlefields
        mine={mine}
        theirs={theirs}
        seat={seat}
        onTap={playable ? act : undefined}
      />
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
