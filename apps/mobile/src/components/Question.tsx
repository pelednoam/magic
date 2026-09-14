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
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from "react-native";

import { colour, space, text } from "../theme";
import type { Asked, RuleText } from "../wire";

import { Panel } from "./Panel";

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
  const ready = typed.trim().length > 0 && !asking;
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
        multiline
        onChangeText={setTyped}
        onSubmitEditing={() => { if (ready) { onAsk(typed.trim()); } }}
        placeholder="Can my creature block that one?"
        placeholderTextColor={colour.quiet}
        style={styles.input}
        value={typed}
      />
      <Pressable
        accessibilityRole="button"
        disabled={!ready}
        onPress={() => { onAsk(typed.trim()); }}
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

function Answer({ reply }: { readonly reply: Asked }) {
  const cited = new Set(reply.answer.citations);
  return (
    <View>
      {reply.cited ? null : (
        <Text style={styles.refused}>
          The answer used a rule the server did not find, so it is not shown. The
          rules below are the real ones — read those.
        </Text>
      )}
      {reply.answer.in_short === "" ? null : (
        <Text style={styles.short}>{reply.answer.in_short}</Text>
      )}
      {reply.answer.answer === "" ? null : (
        <Text style={styles.full}>{reply.answer.answer}</Text>
      )}
      {reply.answer.unsure === "" ? null : (
        <Text style={styles.unsure}>
          {reply.cited ? "Not settled by these rules: " : "Why it was not shown: "}
          {reply.answer.unsure}
        </Text>
      )}
      {reply.rules.length === 0 ? (
        <Text style={styles.none}>Nothing in the Comprehensive Rules matched that.</Text>
      ) : (
        <View style={styles.rules}>
          <Text style={styles.rulesTitle}>
            From the rules — these are the source; the wording above is Claude&apos;s
          </Text>
          {reply.rules.map((rule, at) => (
            <Rule
              key={`${at}-${rule.reference}`}
              rule={rule}
              cited={cited.has(rule.reference)}
            />
          ))}
        </View>
      )}
    </View>
  );
}

/** One retrieved rule. The cited ones are marked, not filtered: a player
 *  reading around the answer is the behaviour this is trying to encourage. */
function Rule({ rule, cited }: { readonly rule: RuleText; readonly cited: boolean }) {
  return (
    <View style={styles.rule}>
      <Text style={[styles.reference, cited ? styles.used : null]}>
        {rule.reference}
        {rule.title === "" || rule.title === rule.reference ? "" : ` · ${rule.title}`}
      </Text>
      <Text style={styles.ruleText}>{rule.text}</Text>
    </View>
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
  refused: { color: colour.warn, fontSize: text.body, marginTop: space.small },
  short: {
    color: colour.text,
    fontSize: text.heading,
    fontWeight: "600",
    marginTop: space.medium,
  },
  full: { color: colour.text, fontSize: text.body, marginTop: space.small },
  unsure: { color: colour.warn, fontSize: text.small, marginTop: space.small },
  none: { color: colour.quiet, fontSize: text.small, marginTop: space.small },
  off: { color: colour.quiet, fontSize: text.body },
  rules: { marginTop: space.medium },
  rulesTitle: {
    color: colour.quiet,
    fontSize: text.small,
    fontWeight: "700",
    marginBottom: space.tight,
  },
  rule: { marginBottom: space.small },
  reference: { color: colour.quiet, fontSize: text.small, fontWeight: "700" },
  used: { color: colour.yes },
  ruleText: { color: colour.text, fontSize: text.small },
});
