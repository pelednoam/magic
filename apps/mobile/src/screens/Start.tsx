/** Pick two decks and begin. The whole of setup. */

import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import type { Coach } from "../client";
import { colour, space, text } from "../theme";
import type { NewGame } from "../wire";

export function Start({
  coach,
  onStarted,
}: {
  readonly coach: Coach;
  readonly onStarted: (game: NewGame) => void;
}) {
  const [decks, setDecks] = useState<readonly string[] | null>(null);
  const [yours, setYours] = useState<string | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    coach
      .decks()
      .then(setDecks)
      .catch((error: unknown) => { setProblem(messageOf(error)); });
  }, [coach]);

  async function begin(theirs: string): Promise<void> {
    if (yours === null) {
      return;
    }
    try {
      onStarted(await coach.start(yours, theirs));
    } catch (error: unknown) {
      setProblem(messageOf(error));
    }
  }

  if (problem !== "") {
    return <Text style={styles.problem}>{problem}</Text>;
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
    </ScrollView>
  );
}

/** An error as a sentence, whatever it turned out to be. */
export function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : "could not reach the server";
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
});
