/**
 * Choosing a played game to step through.
 *
 * Two lists and then the stepper: which run, then which game in it. Small
 * enough to not need a router, and kept apart from `Walk` so that the stepper
 * is only given a game -- it does no fetching, which is what makes it possible
 * to test the thing a child actually looks at.
 *
 * A whole journal arrives in one request. A game is a few hundred kilobytes and
 * stepping should be instant; a request per step would make the back button
 * slower than the forward one, which is the wrong way round for a screen whose
 * whole purpose is going back over something.
 */

import { useEffect, useState } from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text } from "react-native";

import type { Coach } from "../client";
import { messageOf } from "../errors";
import { colour, space, text } from "../theme";
import type { NewGame, PlayedGame, Walkthrough } from "../wire";

import { Walk } from "./Walk";

export function Replays({
  coach,
  onPlay,
  onLeave,
}: {
  readonly coach: Coach;
  /**
   * Carry on from one moment as an ordinary game.
   *
   * The seat goes with it: a moment belongs to whoever was being asked, and
   * opening their turn showing the *other* player's advice would answer a
   * question nobody asked.
   */
  readonly onPlay: (game: NewGame, seat: string) => void;
  readonly onLeave: () => void;
}) {
  const [runs, setRuns] = useState<readonly string[] | null>(null);
  const [name, setName] = useState<string | null>(null);
  const [walk, setWalk] = useState<Walkthrough | null>(null);
  const [chosen, setChosen] = useState<PlayedGame | null>(null);
  const [problem, setProblem] = useState("");

  useEffect(() => {
    coach
      .replays()
      .then(setRuns)
      .catch((error: unknown) => { setProblem(messageOf(error)); });
  }, [coach]);

  async function open(run: string): Promise<void> {
    setName(run);
    try {
      setWalk(await coach.walkthrough(run));
    } catch (error: unknown) {
      setProblem(messageOf(error));
    }
  }

  async function askAbout(index: number): Promise<void> {
    const asked = chosen?.moments[index];
    if (name === null || chosen === null || asked === undefined) {
      return;
    }
    try {
      onPlay(await coach.stepInto(name, chosen.seed, index), asked.player);
    } catch (error: unknown) {
      setProblem(messageOf(error));
    }
  }

  if (problem !== "") {
    return (
      <Page title="That did not work">
        <Text style={styles.problem}>{problem}</Text>
        <Back label="← back" onPress={onLeave} />
      </Page>
    );
  }
  if (chosen !== null) {
    return (
      <Walk
        game={chosen}
        onAsk={(index) => { void askAbout(index); }}
        onLeave={() => { setChosen(null); }}
      />
    );
  }
  if (name !== null) {
    return walk === null ? (
      <ActivityIndicator color={colour.accent} style={styles.loading} />
    ) : (
      <Page title={name}>
        {walk.games.length === 0 ? (
          <Text style={styles.empty}>Nothing in this run can be stepped through.</Text>
        ) : (
          walk.games.map((game) => (
            <Pressable
              key={game.seed}
              accessibilityRole="button"
              onPress={() => { setChosen(game); }}
              style={styles.row}
            >
              <Text style={styles.rowName}>{game.decks.join(" v ")}</Text>
              <Text style={styles.rowNote}>
                {`${game.moments.length} decisions · game ${game.seed}`}
              </Text>
            </Pressable>
          ))
        )}
        <Back
          label="← a different run"
          onPress={() => {
            setName(null);
            setWalk(null);
          }}
        />
      </Page>
    );
  }
  if (runs === null) {
    return <ActivityIndicator color={colour.accent} style={styles.loading} />;
  }
  return (
    <Page title="Games already played">
      {runs.length === 0 ? (
        <Text style={styles.empty}>
          This server has kept no games yet. Play one, or run the self-play harness.
        </Text>
      ) : (
        runs.map((run) => (
          <Pressable
            key={run}
            accessibilityRole="button"
            onPress={() => { void open(run); }}
            style={styles.row}
          >
            <Text style={styles.rowName}>{run}</Text>
          </Pressable>
        ))
      )}
      <Back label="← back" onPress={onLeave} />
    </Page>
  );
}

/** A titled, scrolling list. The shape all three of these states share. */
function Page({
  title,
  children,
}: {
  readonly title: string;
  readonly children: React.ReactNode;
}) {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.title}>{title}</Text>
      {children}
    </ScrollView>
  );
}

/** The way back out of wherever this is. */
function Back({ label, onPress }: { readonly label: string; readonly onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress}>
      <Text style={styles.back}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.large },
  title: {
    color: colour.text,
    fontSize: text.title,
    fontWeight: "700",
    marginBottom: space.medium,
  },
  row: {
    backgroundColor: colour.panel,
    borderColor: colour.panelEdge,
    borderRadius: 8,
    borderWidth: 1,
    marginBottom: space.small,
    padding: space.medium,
  },
  rowName: { color: colour.text, fontSize: text.body, textTransform: "capitalize" },
  rowNote: { color: colour.quiet, fontSize: text.small },
  back: { color: colour.accent, fontSize: text.small, marginTop: space.medium },
  empty: { color: colour.quiet, fontSize: text.body },
  problem: { color: colour.no, fontSize: text.body },
  loading: { marginTop: space.large },
});
