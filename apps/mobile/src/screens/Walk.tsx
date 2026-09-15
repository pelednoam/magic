/**
 * Stepping through a game that already happened, one decision at a time.
 *
 * Built for a child sitting next to somebody, going "what happened here?" --
 * so the two step buttons are the biggest things on the screen, the position is
 * named in words rather than step ids, and what the coach said is read first.
 *
 * Everything shown is what happened. The board was rebuilt from the game's
 * recorded events and the advice is what the coach actually said at the time,
 * so nothing here can differ from the game it is showing. That matters more on
 * this screen than anywhere else in the app, because it is the one somebody
 * learns the rules from.
 *
 * "Ask about this" turns the moment into a real game on the server. From there
 * it is an ordinary session, which is how a question about turn seven gets
 * answered about turn seven's board rather than about a board like it.
 */

import { useState } from "react";
import { Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { Board } from "../components/Board";
import { Said } from "../components/Said";
import { placeOf, seatName } from "../format";
import { colour, space, text } from "../theme";
import type { PlayedGame } from "../wire";
import { THEM, YOU } from "../wire";

export function Walk({
  game,
  onAsk,
  onLeave,
}: {
  readonly game: PlayedGame;
  /** Open this moment as a game, so it can be asked about. */
  readonly onAsk: (index: number) => void;
  readonly onLeave: () => void;
}) {
  const [at, setAt] = useState(0);
  const moment = game.moments[at];
  const mine = moment?.state.players[YOU];
  const theirs = moment?.state.players[THEM];

  if (moment === undefined || mine === undefined || theirs === undefined) {
    return (
      <View style={styles.page}>
        <Text style={styles.nothing}>
          {moment === undefined
            ? "Nothing was asked in this game, so there is nothing to step through."
            : "This game is not one this app can show."}
        </Text>
        <Leave onLeave={onLeave} />
      </View>
    );
  }

  return (
    <View style={styles.page}>
      <Text style={styles.where}>{placeOf(moment.turn, moment.step)}</Text>
      <Text style={styles.counter}>
        {`decision ${at + 1} of ${game.moments.length} · ${game.decks.join(" v ")}`}
      </Text>

      <ScrollView contentContainerStyle={styles.scroll}>
        <Said moment={moment} />
        <Board title={seatName(YOU, "You", moment.player)} player={mine} />
        <Board title={seatName(THEM, "Them", moment.player)} player={theirs} />
      </ScrollView>

      <View style={styles.feet}>
        <Step label="‹ back" to={at - 1} count={game.moments.length} onGo={setAt} />
        <Pressable accessibilityRole="button" onPress={() => { onAsk(at); }}>
          <Text style={styles.ask}>ask about this</Text>
        </Pressable>
        <Step label="next ›" to={at + 1} count={game.moments.length} onGo={setAt} />
      </View>
      <Leave onLeave={onLeave} />
    </View>
  );
}

/** The way back, in one place, because both returns need it. */
function Leave({ onLeave }: { readonly onLeave: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onLeave}>
      <Text style={styles.leave}>← back to the games</Text>
    </Pressable>
  );
}

/** One of the two step buttons, dimmed and inert at the ends. */
function Step({
  label,
  to,
  count,
  onGo,
}: {
  readonly label: string;
  readonly to: number;
  readonly count: number;
  readonly onGo: (index: number) => void;
}) {
  const possible = to >= 0 && to < count;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: !possible }}
      disabled={!possible}
      onPress={() => { onGo(to); }}
    >
      <Text style={possible ? styles.step : styles.stepOff}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: space.medium },
  where: { color: colour.text, fontSize: text.title, fontWeight: "700" },
  counter: { color: colour.quiet, fontSize: text.small, paddingBottom: space.small },
  scroll: { paddingBottom: space.large },
  feet: {
    alignItems: "center",
    borderTopColor: colour.panelEdge,
    borderTopWidth: 1,
    flexDirection: "row",
    justifyContent: "space-between",
    paddingTop: space.medium,
  },
  step: { color: colour.accent, fontSize: text.title, padding: space.small },
  stepOff: { color: colour.panelEdge, fontSize: text.title, padding: space.small },
  ask: { color: colour.accent, fontSize: text.body },
  leave: { color: colour.quiet, fontSize: text.small, paddingTop: space.medium },
  nothing: { color: colour.text, fontSize: text.body, paddingBottom: space.medium },
});
