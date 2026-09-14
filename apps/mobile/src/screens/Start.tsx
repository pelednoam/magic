/** Pick two decks and begin. The whole of setup. */

import { useEffect, useState } from "react";
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";

import type { Coach } from "../client";
import { ServerError } from "../client";
import { messageOf } from "../errors";
import { Trouble } from "../components/Trouble";
import { colour, space, text } from "../theme";
import type { NewGame } from "../wire";
import { THEM, YOU } from "../wire";

export function Start({
  coach,
  onStarted,
  onToken,
}: {
  readonly coach: Coach;
  readonly onStarted: (game: NewGame, seat: string) => void;
  /** Called with a token typed in by hand; see `needsToken` below. */
  readonly onToken: (token: string) => void;
}) {
  const [decks, setDecks] = useState<readonly string[] | null>(null);
  const [yours, setYours] = useState<string | null>(null);
  const [joining, setJoining] = useState("");
  const [problem, setProblem] = useState("");
  /**
   * Whether the server said "you have the wrong token".
   *
   * A build on the same laptop picks the token up from the environment; a
   * phone cannot, so it has to be typed once. Showing the field only when the
   * server has actually refused keeps it out of the way in the common case.
   */
  const [needsToken, setNeedsToken] = useState(false);
  const [typed, setTyped] = useState("");

  const refused = (error: unknown) => {
    setNeedsToken(error instanceof ServerError && error.needsToken);
    setProblem(messageOf(error));
  };

  useEffect(() => {
    setNeedsToken(false);
    setProblem("");
    coach.decks().then(setDecks).catch(refused);
    // `refused` is made fresh each render and only ever sets state.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [coach]);

  async function begin(theirs: string): Promise<void> {
    if (yours === null) {
      return;
    }
    try {
      onStarted(await coach.start(yours, theirs), YOU);
    } catch (error: unknown) {
      refused(error);
    }
  }

  /**
   * Open a game someone else started, as the other player.
   *
   * A game is a session id and anyone on the LAN who has it can open it. This
   * is what makes the second device a second *seat* rather than a second game
   * -- without it the WebSocket and the both-players advice had nothing to be
   * for, because only one device could ever act.
   */
  async function join(): Promise<void> {
    try {
      const existing = await coach.look(joining.trim());
      onStarted({ ...existing, session_id: joining.trim() }, THEM);
    } catch (error: unknown) {
      refused(error);
    }
  }

  if (problem !== "") {
    return (
      <Trouble
        problem={problem}
        needsToken={needsToken}
        typed={typed}
        onTyped={setTyped}
        onRetry={() => {
          setProblem("");
          setDecks(null);
          if (needsToken) {
            // `onToken` hands this screen a new `Coach`, whose arrival the
            // effect above sees and retries with.
            onToken(typed.trim());
            return;
          }
          coach.decks().then(setDecks).catch(refused);
        }}
      />
    );
  }
  if (decks === null) {
    return <ActivityIndicator color={colour.accent} style={styles.loading} />;
  }

  const picking = yours === null;
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.title}>{picking ? "Your deck" : "Their deck"}</Text>
      <View style={styles.list}>
        {decks.map((deck) => (
          <Pressable
            key={deck}
            accessibilityRole="button"
            onPress={() => {
              if (picking) {
                setYours(deck);
              } else {
                void begin(deck);
              }
            }}
            style={styles.deck}
          >
            <Text style={styles.deckName}>{deck}</Text>
          </Pressable>
        ))}
      </View>
      {picking ? null : (
        <Pressable accessibilityRole="button" onPress={() => { setYours(null); }}>
          <Text style={styles.back}>← pick a different deck for yourself</Text>
        </Pressable>
      )}
      {picking ? (
        <View style={styles.join}>
          <Text style={styles.joinTitle}>…or join a game already running</Text>
          <TextInput
            accessibilityLabel="Game code"
            autoCapitalize="none"
            onChangeText={setJoining}
            placeholder="paste the game code"
            placeholderTextColor={colour.quiet}
            style={styles.code}
            value={joining}
          />
          <Pressable
            accessibilityRole="button"
            disabled={joining.trim() === ""}
            onPress={() => { void join(); }}
          >
            <Text style={styles.back}>join as the other player →</Text>
          </Pressable>
        </View>
      ) : null}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.large },
  title: { color: colour.text, fontSize: text.title, fontWeight: "700", marginBottom: space.medium },
  list: { gap: space.small },
  deck: {
    backgroundColor: colour.panel,
    borderColor: colour.panelEdge,
    borderRadius: 8,
    borderWidth: 1,
    padding: space.medium,
  },
  deckName: { color: colour.text, fontSize: text.body, textTransform: "capitalize" },
  back: { color: colour.accent, fontSize: text.small, marginTop: space.medium },
  problem: { color: colour.no, fontSize: text.body, padding: space.large },
  loading: { marginTop: space.large },
  join: { borderTopColor: colour.panelEdge, borderTopWidth: 1, marginTop: space.large,
    paddingTop: space.medium },
  joinTitle: { color: colour.quiet, fontSize: text.small, marginBottom: space.small },
  code: {
    backgroundColor: colour.panel,
    borderColor: colour.panelEdge,
    borderRadius: 8,
    borderWidth: 1,
    color: colour.text,
    marginBottom: space.small,
    padding: space.medium,
  },
});
