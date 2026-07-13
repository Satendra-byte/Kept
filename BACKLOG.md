# Kept backlog

Everything worth building beyond the shipped v1, grouped by priority. The core loop
(detect, confirm, ledger, message action, nudge, reschedule, delay draft, recall) is
built and working. This batch made it sharper. Rough effort in brackets.

**Status:** Tiers 1, 2, and 3 are all built and tested (offline suite + live LLM
checks). Two items ship as code but need a Slack reinstall to activate, flagged below.

## 0. Ship first (before the deadline, not code)

- [x] README with the logo, one-line pitch, differentiators, architecture diagram
- [ ] Clean the test data, one dry-run, record the ~3 min demo video
- [ ] Devpost: submit; add slackhack@salesforce.com + testing@devpost.com to the sandbox
      as members; extend the sandbox archive date; roster eligible teammates only

## 1. Core product gaps (the real "make it worthy" batch)

- [x] Time-specific deadlines: capture a time ("tomorrow 5pm"), store it, nudge at the
      time, show it in the ledger
- [x] Mark kept from anywhere: DM "my promises" (or `kept mine` in a channel) lists open
      ones with Mark kept / Need more time / Edit buttons
- [x] Date picker on the message action: opens a modal to confirm or adjust before tracking
- [x] Resolve @mention recipients to names, not raw IDs
- [x] Reschedule-by-message: a close-worded message with a new date offers to update the
      existing promise instead of making a new row (fuzzy match, human confirms)
- [x] Edit a tracked promise: Edit button now opens a real modal (wording, date, time)
- [x] Overdue escalation: a second, sharper nudge once a promise is past its deadline

## 2. Robustness / production

- [x] Persist in-flight confirmations and drafts in SQLite so a restart doesn't drop them
- [x] Timezone-aware nudges (config.TIMEZONE, defaults Europe/London, override KEPT_TZ)
- [x] Gate the DM recall so "hi" and one-word noise get help, not a wasted search
- [x] Guard against the DM-recall and agent-panel handler both answering (distinct
      surfaces; documented in `_on_dm`)
- [~] Agent panel events: manifest carries the assistant events; needs the Agent
      experience toggle + a reinstall to deliver. DM recall is the working fallback.
- [x] A real test suite beyond the self-checks: `tests/test_kept.py`, 27 tests, offline

## 3. New value

- [x] Weekly client-update digest drafted from the ledger (`kept digest`)
- [~] Onboarding welcome when Kept joins a channel: built (member_joined_channel handler
      + manifest event); needs a reinstall to activate the event
- [x] A "kept rate" metric, promises kept vs slipped, per person (`kept stats`)
- [x] Nudge lead-time: config.NUDGE_LEAD_MINUTES nudges N minutes before a timed deadline

## Needs a reinstall to activate (code is done)

The two `[~]` items above are built but dormant until the Slack app is reinstalled:
the welcome message needs the `member_joined_channel` event granted, and the agent
panel needs the Agent experience toggle. Left for after the deadline to avoid churning
the working deployed app.
