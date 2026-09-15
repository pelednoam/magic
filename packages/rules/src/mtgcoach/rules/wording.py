"""What the rules call the things a beginner says in other words.

One constant per concept, with the reason it earned its place. Split from
``phrasing``, which is now only the patterns that recognise a question -- two
different kinds of decision, and the second is much easier to get wrong.

Every phrase here must actually occur in the Comprehensive Rules.
``tools/check_rules_phrasing.py`` checks that against the installed document,
because a target the rules do not contain adds nothing to a query but noise,
and nothing else would ever notice. "Empty library" is the cautionary example:
the obvious guess for a deck running out, and absent from the document.
"""

from __future__ import annotations

#: The rules' own name for "this creature only just turned up", which is the
#: thing rule 302.6 is about and the thing 302.6 never says. The rules use the
#: phrase twice -- in 302.6 itself and in the glossary entry that points back
#: to it -- so it survives one of them being reworded.
SUMMONING_SICKNESS = "summoning sickness"

#: What the rules call the number a child calls hit points.
LIFE_TOTAL = "life total"

#: The current wording for what a card printed before 2009 called coming into
#: play. Rule 403.5 covers the bare phrase; this finds the rules about the
#: event, which is usually what is being asked about.
ENTERED = "entered the battlefield"

#: The rules' phrase for a player running out of life, which is the one thing
#: a beginner most wants to know and the rules describe in digits: "0 or less
#: life", in 119.6 and 704.5a. A question saying "zero" matched neither, and
#: adding the bare digit was worse -- it pulled in every rule that mentions the
#: {0} mana symbol. The whole phrase is specific enough to rank.
OUT_OF_LIFE = "0 or less life"

#: What the rules call a creature dying, which they define in as many words:
#: CR 700.4, "the term dies means 'is put into a graveyard from the
#: battlefield'". The phrase is what ranks; see ``INSTEAD`` for why the word
#: cannot.
DIES = "put into a graveyard from the battlefield"

#: And why it happened, which is what the question is usually really asking:
#: CR 704.5g and 704.5h.
LETHAL = "lethal damage"

#: The rules' words for a deck running out. "Empty library" is the obvious
#: guess and does not occur in the document at all; CR 121.4 and 704.5b both
#: say "a library with no cards in it".
NO_CARDS = "library with no cards"

#: A spell that needs a target and has none to choose.
#:
#: Two phrases, and the first is the useful one. "Legal target" is the concept
#: and occurs twenty-six times, so it ranks whichever rule about illegal
#: targets happens to score highest. "Each target the spell requires" occurs
#: exactly *once*, in CR 601.2c -- the rule that says the choice has to be
#: announced, and therefore the rule that answers "can I cast this with
#: nothing to point it at". A phrase that appears once is a pointer rather than
#: a search term, which is the most precise thing this map can hold.
TARGET_CHOICE = "each target the spell requires"
LEGAL_TARGET = "legal target"
