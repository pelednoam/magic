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
import { YOU } from "./src/wire";

/**
 * Where the server is. The laptop on the same LAN, by default -- §4's "run it
 * on the laptop over LAN, or a Pi". Overridden at build time for anything else.
 */
const SERVER = process.env["EXPO_PUBLIC_COACH_URL"] ?? "http://localhost:8000";

/**
 * The server's token, if this build was given one.
 *
 * The server prints it at startup; `npm run web` on the same laptop picks it up
 * from the environment. A phone will not have it, which is why `Start` asks
 * for it when the server refuses -- see its `onToken`.
 */
const TOKEN = process.env["EXPO_PUBLIC_COACH_TOKEN"] ?? "";

export default function App() {
  // Held in state rather than derived, because a token typed into `Start`
  // replaces it and everything below needs the new one.
  const [coach, setCoach] = useState(() => new Coach(SERVER, TOKEN));
  const [game, setGame] = useState<NewGame | null>(null);
  // Which side of the table this device is. The first device takes "you"; a
  // device that joins an existing game takes the other seat.
  const [seat, setSeat] = useState(YOU);

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="light" />
      {game === null ? (
        <Start
          coach={coach}
          onStarted={(started, taken) => {
            setSeat(taken);
            setGame(started);
          }}
          onToken={(token) => { setCoach(coach.withToken(token)); }}
        />
      ) : (
        <Game coach={coach} game={game} seat={seat} />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colour.background, flex: 1 },
});
