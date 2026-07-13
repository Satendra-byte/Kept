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

## The LLM only classifies and drafts, it never acts

Every side effect (tracking, nudging, posting) needs a human tap. The LLM reads and
extracts, and it drafts prose (the delay message, the digest), but it never triggers an
action itself.

Why: the message text is untrusted input, so this is where prompt injection could
bite. Keeping the LLM to reading and drafting means the worst a hostile message can do
is be read as a non-promise or shape a draft a human still has to send. Full posture in
SECURITY.md.

## Deadlines can carry a time, and the nudge fires at it

A promise can capture a clock time ("by 5pm" becomes 17:00), and the scheduler fires at
that time, not just on the day. A promise with only a date nudges any time that day.

Why: "by 5pm" and "by end of day" are different promises, and a nudge that fires at 9am
for a 5pm deadline is noise. Firing at the time makes the reminder land when it is
useful. What we did not do: sub-day precision beyond a single same-day lead window, and
the scheduler never nudges and escalates the same promise in one sweep, a promise first
seen already late gets the nudge, not both at once (a bug the test suite caught).

## In-flight cards live in the store, not in memory

A confirmation or draft waiting on a tap is a row in SQLite (pending_confirmations,
pending_drafts), not an entry in a Python dict.

Why: the dicts were wiped on restart, so a card in flight during a redeploy was lost and
the button then said "expired". Persisting them survives a restart. It does not weaken
the storage posture: these are the same structured promises, keyed by an opaque id, with
no raw message text beyond the promise itself. What we did not do: an expiry sweep, a
sandbox does not accumulate enough stale rows to matter; add a TTL if it ever does.

## Reschedule-by-message is a match plus a human tap

When a new message is close-worded to an existing open promise and carries a different
date, Kept offers to move that promise instead of making a new row. The match is a
string-similarity score, and a human still confirms.

Why: "actually the deck is Wednesday not Monday" should update the deck promise, not add
a second one. But linking a new message to an old promise is a guess, so a fuzzy match
(difflib, a 0.6 threshold) narrows it and the tap makes the call. What we did not do: ask
the LLM to decide it is a reschedule, that is the same cross-message negotiation-reading
we avoid elsewhere, and a wrong auto-merge is worse than a duplicate. It only fires when
the date actually changes, so re-stating the same promise is a no-op.

## Commands are plain text, not slash commands

`kept digest`, `kept stats`, `kept help`, and a `my promises` DM are matched from message
text (a "kept" prefix or an @Kept mention), not registered slash commands.

Why: a slash command needs an app-config change and a reinstall to add. Text triggers
need neither and are discoverable from the pinned note; in a DM the same words work
without the prefix. What we did not do: a `/kept` slash command, it buys a nicer
autocomplete at the cost of a reinstall we did not want before the deadline.

## Nudges run on the workspace clock

All nudge timing is computed in the workspace timezone (`config.TIMEZONE`), not the
server's local time.

Why: "due 5pm" has to mean 5pm where the team is, not 5pm wherever the laptop runs. What
we did not do: per-user timezones, one workspace timezone is right for a shared channel
ledger; per-user only matters once nudges become personal across regions.

## Testable by construction

The pure logic (store, scheduler timing, extractor gating, ledger, blocks, recall terms,
command parsing) is covered by an offline pytest suite that mocks the LLM and Slack, and
the app module imports with token verification off so it loads without network.

Why: the Slack and Gemini paths cannot run in CI, but the logic that actually breaks a
demo can, and the suite caught a real scheduler double-fire on its first run. What we did
not do: integration tests against a live Slack or Gemini, the per-module self-checks and
a manual walkthrough cover those, and mocking a whole workspace is more scaffold than it
is worth here.
