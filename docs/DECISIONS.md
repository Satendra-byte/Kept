# Kept, design decisions

Why Kept is built the way it is. BUILDLOG says what changed and when; this says what
we decided and why, so it can be studied and explained. Each entry is the decision,
the reason, and the thing we deliberately did not do.

## The ledger is shared, not private

The Promise Ledger is one canvas per channel. Everyone in the channel sees the same
rows. It is not per person.

Why: Kept is not a personal todo list, it is a shared record of what the team owes.
The value is that everyone can see it: the account manager sees what a teammate
committed to, the client sees what they are owed. A per-person ledger would just be a
private reminder, which Slack already has. What stays private is the confirm card
(only the promise-maker is asked). Consent is private, the record is shared. A channel
canvas is one shared document anyway, so per-person content is not even possible on it.

## Two ways a promise gets tracked

Auto-detect offers, the message action grabs.

- Auto-detect: Kept reads messages and, when it sees a likely promise, pops a private
  card to the person who made it. They tap Track or ignore it.
- Message action: anyone hovers any message and picks "Track as promise". Kept
  extracts and files it, owner set to whoever wrote the message.

Why both: auto-detect is the passive net for your own promises. The message action is
the deliberate tool for everything auto-detect cannot judge: a promise someone else
made, one that formed across a back-and-forth, or a proposal that only became real
later. The human tap is the judgement call.

## Said versus agreed

A proposal ("can we meet Sunday?") is not a commitment until the other person agrees.
Kept never auto-commits a proposal. If it is agreed later, a human tracks it with the
message action at that moment.

Why not auto-detect the acceptance: making Kept watch for "yes" and link it back to
the right earlier proposal is negotiation-understanding across messages. It mislinks
when there is other chatter, or more than one open proposal, and a tracker that
records the wrong promise is worse than one that asks you to point. The reliable
future version is thread-based: reply "yes" in the proposal's thread, and the hard
thread link tells Kept what was agreed with no guessing.

## Recipient comes from a signal, never a guess

The "To" on a promise is filled only when the message names someone: an @mention or a
direct address ("Sam, I'll ..."). Otherwise it is blank.

Why: "I'll send you the deck" in a five-person channel has no reliable recipient, a
human could not say who "you" is without more context. Letting the LLM guess produces
confident wrong data. Blank is honest, a named recipient is trustworthy.

## Precision over recall, but lean yes

The extractor surfaces anything with a concrete action, then lets the human decide
with one tap. It still drops pure noise: questions, greetings, past events, chat.

Why: a tracker that cries wolf on non-promises trains people to mute it, so precision
matters. But the one-tap confirm makes a borderline yes cheap and a miss expensive, so
the bar is "is there a concrete thing to do", not "is this a formal deliverable". The
human tap is the real filter.

## The LLM does no calendar math

The extractor is handed the real dates for the week ("Monday: 2026-07-13") and looks
the day up, instead of computing it.

Why: the model got weekdays wrong (Monday came back as a Tuesday). Handing it the
dates removes the unreliable step. Deterministic where we can be, LLM only where we
must be.

## SQLite is the source of truth, the canvas is the view

Confirmed promises live in SQLite. The canvas is regenerated from them in full on
every change. Kept never reads the canvas back.

Why: the scheduler needs a reliable store to know what is due, a human-editable canvas
is not that. Full-replace regeneration means no section bookkeeping to drift. And it
lets us say honestly: no raw Slack content is stored outside Slack, only confirmed
structured promises.

## The LLM only classifies, it never acts

Every side effect (tracking, nudging, drafting) needs a human tap. The LLM reads and
extracts, it never triggers an action.

Why: the message text is untrusted input, so this is where prompt injection could
bite. Keeping the LLM to classification means the worst a hostile message can do is be
read as a non-promise. Full posture in SECURITY.md.
