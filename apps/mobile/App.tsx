/**
 * The whole app: pick decks and track a game, or walk one that already happened.
 *
 * Still no router. Three screens and two ways between them, and a navigation
 * library would be more code than the thing it navigates. `Replays` owns the
 * lists inside itself for the same reason.
 */

import { useState } from "react";
import { SafeAreaView, StyleSheet } from "react-native";
import { StatusBar } from "expo-status-bar";

import { Coach } from "./src/client";
import { Game } from "./src/screens/Game";
import { Replays } from "./src/screens/Replays";
import { Start } from "./src/screens/Start";
import { colour } from "./src/theme";
import type { NewGame } from "./src/wire";

/**
 * Where the server is. The laptop on the same LAN, by default -- §4's "run it
 * on the laptop over LAN, or a Pi". Overridden at build time for anything else.
 */
const SERVER = process.env["EXPO_PUBLIC_COACH_URL"] ?? "http://localhost:8000";

/**
 * This device's token, if this build was given one.
 *
 * The server prints one per seat at startup; `npm run web` on the same laptop
 * picks one up from the environment. A phone will not have it, which is why
 * `Start` asks for it when the server refuses -- see its `onToken`.
 *
 * The token is also which player this device *is*: the server reads the seat
 * off it and puts it in every payload. Nothing here chooses a seat any more.
 */
const TOKEN = process.env["EXPO_PUBLIC_COACH_TOKEN"] ?? "";

export default function App() {
  // Held in state rather than derived, because a token typed into `Start`
  // replaces it and everything below needs the new one.
  const [coach, setCoach] = useState(() => new Coach(SERVER, TOKEN));
  const [game, setGame] = useState<NewGame | null>(null);
  // Whether the replay lists are open. Not a screen a game can be in, so it is
  // its own flag rather than another value of `game`.
  const [browsing, setBrowsing] = useState(false);

  // No seat here. It was held in state and chosen by which button was pressed
  // -- start a game and you were "you", join one and you were "them" -- so a
  // device set to the wrong one was a device acting as the other player. It
  // comes off the snapshot now, which comes off the token.
  const begin = (started: NewGame) => {
    setGame(started);
    setBrowsing(false);
  };

  return (
    <SafeAreaView style={styles.screen}>
      <StatusBar style="light" />
      {game !== null ? (
        <Game coach={coach} game={game} />
      ) : browsing ? (
        <Replays coach={coach} onPlay={begin} onLeave={() => { setBrowsing(false); }} />
      ) : (
        <Start
          coach={coach}
          onStarted={begin}
          onReplays={() => { setBrowsing(true); }}
          onToken={(token) => { setCoach(coach.withToken(token)); }}
        />
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  screen: { backgroundColor: colour.background, flex: 1 },
});
