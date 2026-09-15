/**
 * Your hand, with the engine's verdict on each card.
 *
 * The heart of the thing. Not "these are your cards" but, for every one of
 * them, whether you can play it now and -- when you cannot -- the sentence the
 * engine wrote saying why. Those sentences are printed verbatim; this component
 * has no idea what a land is.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { paymentLine } from "../format";
import { colour, space, text } from "../theme";
import type { Playable, Player } from "../wire";

import { Panel } from "./Panel";

export function Hand({
  cards,
  board,
  onPlay,
}: {
  readonly cards: readonly Playable[];
  readonly board: Player;
  /**
   * What to do when a card is tapped. Absent means nothing can be played --
   * a finished game, where the server refuses every event, so offering the
   * tap would produce a refusal for no reason the player could see.
   */
  readonly onPlay?: ((card: Playable) => void) | undefined;
}) {
  const ready = cards.filter((card) => card.playable).length;
  return (
    <Panel title="Your hand" note={`${ready} of ${cards.length} playable`}>
      {cards.length === 0 ? (
        <Text style={styles.empty}>Nothing in hand.</Text>
      ) : (
        cards.map((card) => (
          <HandCard key={card.instance_id} card={card} board={board} onPlay={onPlay} />
        ))
      )}
    </Panel>
  );
}

function HandCard({
  card,
  board,
  onPlay,
}: {
  readonly card: Playable;
  readonly board: Player;
  readonly onPlay?: ((card: Playable) => void) | undefined;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={`${card.name}, ${card.playable ? "playable" : "not playable"}`}
      disabled={!card.playable || onPlay === undefined}
      onPress={() => { onPlay?.(card); }}
      style={[styles.card, card.playable ? styles.can : styles.cannot]}
    >
      <View style={styles.row}>
        <Text style={styles.name}>{card.name}</Text>
        <Text style={card.playable ? styles.yes : styles.no}>
          {card.playable ? "can play" : "cannot"}
        </Text>
      </View>
      {card.reasons.map((reason) => (
        <Text key={reason} style={styles.reason}>
          {reason}
        </Text>
      ))}
      {/* Not a reason you cannot play it. A warning that the tracker will not
          show what happens when you do, so the board on screen will be behind
          the board on the table until you fix it by hand. */}
      {card.not_carried_out.map((undone) => (
        <Text key={undone} style={styles.undone}>
          {`The tracker will not apply ${undone} — do it on the table.`}
        </Text>
      ))}
      {card.payment === null ? null : (
        <Text style={styles.payment}>
          {paymentLine(board, card.payment.tap, card.payment.keep)}
        </Text>
      )}
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderLeftWidth: 3,
    borderRadius: 6,
    marginBottom: space.small,
    paddingHorizontal: space.small,
    paddingVertical: space.small,
  },
  can: { backgroundColor: "#172a20", borderLeftColor: colour.yes },
  cannot: { backgroundColor: "#241a1d", borderLeftColor: colour.no },
  row: { flexDirection: "row", justifyContent: "space-between" },
  name: { color: colour.text, fontSize: text.body, fontWeight: "600" },
  yes: { color: colour.yes, fontSize: text.small },
  no: { color: colour.no, fontSize: text.small },
  reason: { color: colour.quiet, fontSize: text.small, marginTop: space.tight },
  undone: { color: colour.warn, fontSize: text.small, marginTop: space.tight },
  payment: { color: colour.accent, fontSize: text.small, marginTop: space.tight },
  empty: { color: colour.quiet, fontSize: text.body },
});
