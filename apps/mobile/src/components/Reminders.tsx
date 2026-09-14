/**
 * Triggers about to be missed, and cards the coach cannot speak for.
 *
 * Two sections that look alike and mean opposite things. The first is the
 * engine being useful; the second is it being honest -- at 52% of the box
 * modelled, a player who is not told where the coach stops will read its
 * silence as "there is nothing to do".
 */

import { StyleSheet, Text } from "react-native";

import { colour, space, text } from "../theme";
import type { Reminder } from "../wire";

import { Panel } from "./Panel";

export function Reminders({ reminders }: { readonly reminders: readonly Reminder[] }) {
  if (reminders.length === 0) {
    return null;
  }
  return (
    <Panel title="Do not forget">
      {reminders.map((reminder) => (
        <Text key={reminder.instance_id} style={styles.trigger}>
          {reminder.name} triggers now
        </Text>
      ))}
    </Panel>
  );
}

export function Unknown({ cards }: { readonly cards: readonly string[] }) {
  if (cards.length === 0) {
    return null;
  }
  return (
    <Panel title="The coach cannot speak for these">
      {cards.map((card) => (
        <Text key={card} style={styles.unknown}>
          {card}
        </Text>
      ))}
      <Text style={styles.caveat}>Read these yourself; the advice above leaves them out.</Text>
    </Panel>
  );
}

const styles = StyleSheet.create({
  trigger: { color: colour.warn, fontSize: text.body, marginBottom: space.tight },
  unknown: { color: colour.text, fontSize: text.body, marginBottom: space.tight },
  caveat: { color: colour.quiet, fontSize: text.small, marginTop: space.tight },
});
