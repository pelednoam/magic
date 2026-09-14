/**
 * The tracker. One screen, one turn at a time.
 *
 * Every action is an *event* sent to the server, which decides what it means
 * and sends the whole board back (§4). Nothing is applied optimistically: the
 * server is the game, and a tracker that guessed ahead of it would be a second
 * rules engine written in the language chosen for not having one.
 */

import { useCallback, useEffect, useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Attacks } from "../components/Attacks";
import { Board } from "../components/Board";
import { Hand } from "../components/Hand";
import { Reminders, Unknown } from "../components/Reminders";
import type { Coach } from "../client";
import { turnLine } from "../format";
import { colour, space, text } from "../theme";
import type { NewGame, Permanent, Playable, Snapshot } from "../wire";
import { THEM, YOU } from "../wire";

import { messageOf } from "./Start";

export function Game({ coach, game }: { readonly coach: Coach; readonly game: NewGame }) {
  const [snapshot, setSnapshot] = useState<Snapshot>(game);
  const [problem, setProblem] = useState("");

  // The socket is the other device's changes arriving. Our own come back from
  // the request that caused them, so there is one path for each and neither
  // has to guess.
  const [watching, setWatching] = useState(true);
  useEffect(() => {
    const socket = new WebSocket(coach.watchUrl(game.session_id));
    socket.onopen = () => { setWatching(true); };
    socket.onmessage = (message: MessageEvent<string>) => {
      try {
        setSnapshot(JSON.parse(message.data) as Snapshot);
      } catch {
        // A frame we cannot read is a broken server, not a broken game. The
        // board on screen is still the last one the server confirmed.
        setWatching(false);
      }
    };
    // A board that has stopped updating must not keep looking live: the other
    // device's plays would simply stop appearing, with nothing to say so.
    socket.onclose = () => { setWatching(false); };
    socket.onerror = () => { setWatching(false); };
    return () => { socket.close(); };
  }, [coach, game.session_id]);

  const act = useCallback(
    async (event: Record<string, unknown>): Promise<void> => {
      setProblem("");
      try {
        setSnapshot(await coach.event(game.session_id, event));
      } catch (error: unknown) {
        setProblem(messageOf(error));
      }
    },
    [coach, game.session_id],
  );

  const mine = snapshot.state.players[YOU];
  const theirs = snapshot.state.players[THEM];
  const advice = snapshot.advice[YOU];
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
          void act({ type: "play_land", player: YOU, instance_id: card.instance_id });
        }}
      />
      <Attacks attacks={advice.attacks} />
      <Board
        title="Your battlefield"
        player={mine}
        onTap={(permanent: Permanent) => {
          void act({
            type: "set_tapped",
            player: YOU,
            instance_id: permanent.instance_id,
            tapped: !permanent.tapped,
          });
        }}
      />
      <Board title="Their battlefield" player={theirs} />
      <Unknown cards={advice.unknown} />

      <View style={styles.controls}>
        <Action label="Next step" onPress={() => { void act({ type: "advance_step" }); }} />
        <Action
          label="Draw"
          onPress={() => { void act({ type: "draw_card", player: YOU }); }}
        />
        <Action
          label="Undo"
          onPress={() => {
            setProblem("");
            coach
              .undo(game.session_id)
              .then(setSnapshot)
              .catch((error: unknown) => { setProblem(messageOf(error)); });
          }}
        />
      </View>
    </ScrollView>
  );
}

function Action({
  label,
  onPress,
}: {
  readonly label: string;
  readonly onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.action}>
      <Text style={styles.actionLabel}>{label}</Text>
    </Pressable>
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
  controls: { flexDirection: "row", gap: space.small },
  action: {
    backgroundColor: colour.accent,
    borderRadius: 8,
    flex: 1,
    paddingVertical: space.medium,
  },
  actionLabel: {
    color: "#0d1016",
    fontSize: text.body,
    fontWeight: "700",
    textAlign: "center",
  },
});
