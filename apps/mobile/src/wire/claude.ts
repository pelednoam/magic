/**
 * What Claude said, and what the server checked before passing it on.
 *
 * Separate from the board types because these are the only payloads that began
 * life inside a language model. Each carries a flag saying what the server was
 * able to check, and the two flags are deliberately different words: a turn
 * recommendation is `trusted` because the engine agreed with the *choice*, and
 * a rules answer is only `cited` because a citation is not a proof. The guards
 * below are the second half of the check -- a cast is a claim, and this is
 * where the claim gets tested.
 */

import { asObject, isStrings } from "./shapes";

/**
 * What Claude said about a turn, once the engine has checked it.
 *
 * `play` and `attack` are identifiers, not names: they are a *choice among the
 * options above*, and the server rejected the answer outright if they were
 * anything else. The app looks them up in `advice.hand` and `advice.attacks`
 * rather than printing them, so a coached recommendation and the engine's own
 * list are always talking about the same card.
 */
export interface Explanation {
  /** An `instance_id` from `advice.hand`, or empty for "play nothing". */
  readonly play: string;
  /** `instance_id`s matching one of `advice.attacks.plans`. */
  readonly attack: readonly string[];
  /** Two or three sentences for whoever is teaching. */
  readonly because: string;
  /** One or two sentences for whoever is learning. §3's whole point. */
  readonly in_short: string;
  /**
   * Things that will go wrong if they are not noticed — or, when `trusted` is
   * false, the checker's own objections to the answer it replaced. The panel
   * labels them differently in that case, because "the coach recommended a
   * card that is not in your hand" is not a warning about the game.
   */
  readonly watch_out: readonly string[];
  /** What the engine could not work out. Shown, never hidden. */
  readonly check_yourself: readonly string[];
}

/** The coach route's reply. */
export interface Coaching {
  readonly explanation: Explanation;
  /**
   * Whether the engine agreed with what the coach said.
   *
   * False means `explanation` is the refusal text, not advice: the model
   * recommended something the engine had not offered, and the server replaced
   * it. The screen has to say so -- showing a refusal as though it were advice
   * is the one failure this whole layer exists to prevent.
   */
  readonly trusted: boolean;
  /**
   * Which board this is about.
   *
   * Answering takes a minute, which is long enough for somebody to play a
   * card. Comparing this against the snapshot on screen is how a late answer
   * is recognised — the alternative was the client remembering the version it
   * *had* when it asked, which is close enough in practice and still a guess.
   */
  readonly version: number;
}

/**
 * One rule the server retrieved for a question, quoted verbatim.
 *
 * The certainly-true half of an answer. These are shown whatever the model
 * said, and whether or not it cited them: a player who can read 702.19b for
 * themselves does not need to trust anybody about trample.
 */
export interface RuleText {
  /** How it is cited: "702.19b", or a term for a glossary entry. */
  readonly reference: string;
  /** The heading it sits under. "Trample", "Combat Damage Step". */
  readonly title: string;
  readonly text: string;
}

/** What Claude said about a rules question, once its citations were checked. */
export interface RulesAnswer {
  readonly answer: string;
  /** The same thing for the person being taught. */
  readonly in_short: string;
  /** References into `Asked.rules`. Never invented: the server checked. */
  readonly citations: readonly string[];
  /** Where the answer stops. Empty when the rules given settled it. */
  readonly unsure: string;
}

/** The rules question route's reply. */
export interface Asked {
  readonly answer: RulesAnswer;
  /**
   * Whether every rule the answer named was one the server retrieved for it.
   *
   * **Not** whether the answer is right about what those rules say — nothing
   * reads the rule and checks the claim against it, and calling this `trusted`
   * would promise a child something nobody verified. False means `answer` is
   * the refusal text: the model cited a rule nobody retrieved, or cited none
   * at all. `rules` is populated either way, so the question is never lost --
   * the player reads the rule instead of the answer.
   */
  readonly cited: boolean;
  readonly rules: readonly RuleText[];
  /** Which board this was asked over; see `Coaching.version`. */
  readonly version: number;
}

/**
 * Whether a decoded response is shaped like the coach's reply.
 *
 * Same reasoning as `isSnapshot`, and more necessary: this payload started life
 * inside a language model, and the only thing between it and the screen is the
 * server's check and this one.
 */
export function isCoaching(value: unknown): value is Coaching {
  const body = asObject(value);
  if (
    body === null ||
    typeof body["trusted"] !== "boolean" ||
    typeof body["version"] !== "number"
  ) {
    return false;
  }
  const explanation = asObject(body["explanation"]);
  if (explanation === null) {
    return false;
  }
  return (
    typeof explanation["play"] === "string" &&
    typeof explanation["because"] === "string" &&
    typeof explanation["in_short"] === "string" &&
    isStrings(explanation["attack"]) &&
    isStrings(explanation["watch_out"]) &&
    isStrings(explanation["check_yourself"])
  );
}

/** Whether a decoded response is shaped like a rules answer. */
export function isAsked(value: unknown): value is Asked {
  const body = asObject(value);
  if (
    body === null ||
    typeof body["cited"] !== "boolean" ||
    typeof body["version"] !== "number" ||
    !Array.isArray(body["rules"])
  ) {
    return false;
  }
  const answer = asObject(body["answer"]);
  if (answer === null) {
    return false;
  }
  return (
    typeof answer["answer"] === "string" &&
    typeof answer["in_short"] === "string" &&
    typeof answer["unsure"] === "string" &&
    isStrings(answer["citations"]) &&
    body["rules"].every(isRuleText)
  );
}

/** One retrieved rule, checked down to what the screen prints. */
function isRuleText(value: unknown): value is RuleText {
  const rule = asObject(value);
  return (
    rule !== null &&
    typeof rule["reference"] === "string" &&
    typeof rule["title"] === "string" &&
    typeof rule["text"] === "string"
  );
}
