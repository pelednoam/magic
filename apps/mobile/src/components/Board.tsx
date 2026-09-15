/**
 * One player's battlefield, and the two states that stop a permanent acting.
 *
 * The stack used to be here too, one line per player, because it was a field
 * on each player. It is one shared, ordered zone (CR 405.1) and has its own
 * panel now -- `Priority`, which shows the order, whose moment it is, and the
 * buttons that move it on. Two half-stacks in two panels could not say which
 * spell resolves first, which is the only thing that moment is about.
 */

import { Pressable, StyleSheet, Text, View } from "react-native";

import { permanentNote } from "../format";
import { colour, space, text } from "../theme";
import type { Permanent, Player } from "../wire";

import { Panel } from "./Panel";

/**
 * The numbers under a battlefield's title.
 *
 * The hand *count* is here for both players, because how many cards somebody
 * is holding is public (CR 400.2 hides the contents, not the number) and is
 * the thing a player at a table actually counts. The contents arrive for one
 * of them; `Hand` shows those.
 */
function boardNote(player: Player): string {
  return `${player.life} life · ${player.hand_size} in hand · ${player.library} in library`;
}

export function Board({
  title,
  player,
  onTap,
}: {
  readonly title: string;
  readonly player: Player;
  // `| undefined` spelled out because `exactOptionalPropertyTypes` is on: a
  // caller computing the handler (`playable ? tap : undefined`) is passing
  // undefined, which is different from not passing the prop at all.
  readonly onTap?: ((permanent: Permanent) => void) | undefined;
}) {
  return (
    <Panel title={title} note={boardNote(player)}>
      {player.battlefield.length === 0 ? (
        <Text style={styles.empty}>Nothing on the battlefield.</Text>
      ) : (
        <View style={styles.grid}>
          {player.battlefield.map((permanent) => (
            <Pressable
              key={permanent.instance_id}
              accessibilityRole="button"
              accessibilityLabel={`${permanent.name}${permanent.tapped ? ", tapped" : ""}`}
              disabled={onTap === undefined}
              onPress={() => onTap?.(permanent)}
              style={[styles.permanent, permanent.tapped ? styles.tapped : null]}
            >
              <Text style={styles.name}>{permanent.name}</Text>
              {permanentNote(permanent) === "" ? null : (
                <Text style={styles.note}>{permanentNote(permanent)}</Text>
              )}
            </Pressable>
          ))}
        </View>
      )}
    </Panel>
  );
}

const styles = StyleSheet.create({
  grid: { flexDirection: "row", flexWrap: "wrap", gap: space.small },
  permanent: {
    backgroundColor: "#222839",
    borderRadius: 6,
    paddingHorizontal: space.small,
    paddingVertical: space.tight,
  },
  tapped: { backgroundColor: "#2c2430", opacity: 0.65 },
  name: { color: colour.text, fontSize: text.small, fontWeight: "600" },
  note: { color: colour.quiet, fontSize: text.small },
  empty: { color: colour.quiet, fontSize: text.body },
});
