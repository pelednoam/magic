/**
 * The whole app: pick decks, then track a game.
 *
 * No router. There are two screens and one transition between them, and a
 * navigation library would be more code than the thing it navigates.
 */

import { useState } from "react";
import { SafeAreaView, StyleSheet } from "react-native";
import { StatusBar } from "expo-status-bar";

import { Coach } from "./src/client";
import { Game } from "./src/screens/Game";
import { Start } from "./src/screens/Start";
import { colour } from "./src/theme";
import type { NewGame } from "./src/wire";

/**
 * Where the server is. The laptop on the same LAN, by default -- §4's "run it
 * on the laptop over LAN, or a Pi". Overridden at build time for anything else.
 */
const SERVER = process.env["EXPO_PUBLIC_COACH_URL"] ?? "http://localhost:8000";

export default function App() {
  const [coach] = useState(() => new Coach(SERVER));
  const [game, setGame] = useState<NewGame | null>(null);

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="light" />
      {game === null ? (
        <Start coach={coach} onStarted={setGame} />
      ) : (
        <Game coach={coach} game={game} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colour.background, flex: 1 },
});
