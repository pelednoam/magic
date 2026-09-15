/**
 * A titled list of things to pick from, and the way back out.
 *
 * Three small pieces rather than one, because `Replays` is three lists in a
 * row — which runs, which game, and then the stepper — and each state wants
 * the same shape with different words in it.
 */

import type { ReactNode } from "react";
import { Pressable, ScrollView, StyleSheet, Text } from "react-native";

import { colour, space, text } from "../theme";

/** A titled, scrolling page. */
export function Page({
  title,
  children,
}: {
  readonly title: string;
  readonly children: ReactNode;
}) {
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.title}>{title}</Text>
      {children}
    </ScrollView>
  );
}

/** One thing to choose, with an optional second line about it. */
export function Row({
  name,
  note,
  onPress,
}: {
  readonly name: string;
  // `| undefined` spelled out because `exactOptionalPropertyTypes` is on.
  readonly note?: string | undefined;
  readonly onPress: () => void;
}) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.row}>
      <Text style={styles.rowName}>{name}</Text>
      {note === undefined ? null : <Text style={styles.rowNote}>{note}</Text>}
    </Pressable>
  );
}

/** The way back out of wherever this is. */
export function Back({
  label,
  onPress,
}: {
  readonly label: string;
  readonly onPress: () => void;
}) {
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
});
