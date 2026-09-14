/**
 * The rules question box, and what came back.
 *
 * The answer is never the only thing on screen. The passages the server
 * retrieved are shown underneath it, verbatim, whether or not the model cited
 * them -- those are certainly true, and a parent who can read 702.19b does not
 * have to trust anybody about trample. When the check fails, the passages are
 * all that is left, and that is still a useful answer to a rules question.
 */

import { useState } from "react";
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput } from "react-native";

import { colour, space, text } from "../theme";
import type { Asked } from "../wire";

import { Panel } from "./Panel";
import { Answer } from "./RulesAnswer";

/**
 * The same limit the server enforces, so it is seen while typing rather than
 * discovered as a 400 after a wait. Duplicated on purpose -- the server's copy
 * is the one that matters and stays; this one only saves a round trip.
 */
const MAX_QUESTION = 500;

export function Question({
  reply,
  asking,
  problem,
  available,
  onAsk,
}: {
  /** Null until something has been asked. */
  readonly reply: Asked | null;
  readonly asking: boolean;
  /** The server's own sentence when there was no answer at all. */
  readonly problem: string;
  /** Whether this server has the Comprehensive Rules installed at all. */
  readonly available: boolean;
  readonly onAsk: (question: string) => void;
}) {
  const [typed, setTyped] = useState("");
  const asked = typed.trim();
  const tooLong = asked.length > MAX_QUESTION;
  const ready = asked.length > 0 && !tooLong && !asking;
  if (!available) {
    // Said before anybody types, not after they wait for a 503. The rules are
    // an optional install and everything else on this screen works without
    // them, so this is a missing feature rather than a broken one.
    return (
      <Panel title="Ask about the rules">
        <Text style={styles.off}>
          This server does not have the Comprehensive Rules installed, so rules
          questions are switched off. Everything else on this screen still works.
        </Text>
      </Panel>
    );
  }
  return (
    <Panel title="Ask about the rules" note={asking ? "looking it up…" : undefined}>
      <TextInput
        accessibilityLabel="Your rules question"
        editable={!asking}
        maxLength={MAX_QUESTION}
        multiline
        onChangeText={setTyped}
        onSubmitEditing={() => { if (ready) { onAsk(asked); } }}
        placeholder="Can my creature block that one?"
        placeholderTextColor={colour.quiet}
        style={styles.input}
        value={typed}
      />
      {tooLong ? (
        <Text style={styles.problem}>
          That is {asked.length} characters; keep it under {MAX_QUESTION}.
        </Text>
      ) : null}
      <Pressable
        accessibilityRole="button"
        disabled={!ready}
        onPress={() => { onAsk(asked); }}
        style={[styles.ask, ready ? null : styles.waiting]}
      >
        {asking ? (
          <ActivityIndicator color={colour.text} />
        ) : (
          <Text style={styles.askLabel}>Ask</Text>
        )}
      </Pressable>
      {problem === "" ? null : <Text style={styles.problem}>{problem}</Text>}
      {reply === null ? null : <Answer reply={reply} />}
    </Panel>
  );
}

const styles = StyleSheet.create({
  input: {
    backgroundColor: colour.background,
    borderColor: colour.panelEdge,
    borderRadius: 8,
    borderWidth: 1,
    color: colour.text,
    fontSize: text.body,
    marginBottom: space.small,
    minHeight: 44,
    padding: space.small,
  },
  ask: {
    backgroundColor: colour.accent,
    borderRadius: 8,
    justifyContent: "center",
    minHeight: 44,
    paddingVertical: space.small,
  },
  waiting: { backgroundColor: colour.panelEdge },
  askLabel: {
    color: "#0d1016",
    fontSize: text.body,
    fontWeight: "700",
    textAlign: "center",
  },
  problem: { color: colour.no, fontSize: text.body, marginTop: space.small },
  off: { color: colour.quiet, fontSize: text.body },
});
