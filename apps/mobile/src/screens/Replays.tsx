/**
 * Choosing a played game to step through.
 *
 * Two lists and then the stepper: which run, then which game in it. Small
 * enough to not need a router, and kept apart from `Walk` so that the stepper
 * is only given a game — it does no fetching, which is what makes it possible
 * to test the thing a child actually looks at.
 *
 * A game is fetched whole and separately from the list of them. The list needs
 * the decks and a count; the game needs every board, which for a twelve-game
 * season is several megabytes. So the list is small and stepping is instant,
 * and the back button is exactly as fast as the forward one.
 *
 * Everything slow here is guarded against arriving late. Choosing a game and
 * then going back used to leave a fetch in flight that put the screen back
 * where it had just left.
 */

import { useEffect, useState } from "react";
import { ActivityIndicator, StyleSheet, Text } from "react-native";

import type { Coach } from "../client";
import { Back, Page, Row } from "../components/Choosing";
import { messageOf } from "../errors";
import { colour, space, text } from "../theme";
import { useLatest } from "../thinking";
import type { GameLine, NewGame, PlayedGame, Walkthrough } from "../wire";

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

  // Which request the screen is waiting for. A reply carrying an older token
  // is dropped: leaving a list while its game is loading used to put the
  // screen back where it had just left, a second after leaving.
  const latest = useLatest();

  useEffect(() => {
    const current = latest();
    coach
      .replays()
      .then((found) => { if (current()) { setRuns(found); } })
      .catch((error: unknown) => { if (current()) { setProblem(messageOf(error)); } });
  }, [coach, latest]);

  async function open(run: string): Promise<void> {
    const current = latest();
    setName(run);
    try {
      const found = await coach.walkthrough(run);
      if (current()) {
        setWalk(found);
      }
    } catch (error: unknown) {
      if (current()) {
        setProblem(messageOf(error));
      }
    }
  }

  async function show(line: GameLine): Promise<void> {
    const current = latest();
    if (name === null) {
      return;
    }
    try {
      const game = await coach.game(name, line.index);
      if (current()) {
        setChosen(game);
      }
    } catch (error: unknown) {
      if (current()) {
        setProblem(messageOf(error));
      }
    }
  }

  async function askAbout(at: number): Promise<void> {
    const current = latest();
    const asked = chosen?.moments[at];
    if (name === null || chosen === null || asked === undefined) {
      return;
    }
    try {
      const started = await coach.stepInto(name, chosen.index, at);
      if (current()) {
        onPlay(started, asked.player);
      }
    } catch (error: unknown) {
      if (current()) {
        setProblem(messageOf(error));
      }
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
        onAsk={(at) => { void askAbout(at); }}
        onLeave={() => { latest(); setChosen(null); }}
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
          walk.games.map((line) => (
            <Row
              key={line.index}
              name={line.decks.join(" v ")}
              note={`${line.decisions} decisions · game ${line.seed}`}
              onPress={() => { void show(line); }}
            />
          ))
        )}
        <Back
          label="← a different run"
          onPress={() => {
            latest();
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
          <Row key={run} name={run} onPress={() => { void open(run); }} />
        ))
      )}
      <Back label="← back" onPress={onLeave} />
    </Page>
  );
}

const styles = StyleSheet.create({
  empty: { color: colour.quiet, fontSize: text.body },
  problem: { color: colour.no, fontSize: text.body },
  loading: { marginTop: space.large },
});
