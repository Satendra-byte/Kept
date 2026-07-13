# Kept, architecture

The technical design. Security lives in SECURITY.md; this doc is the component map,
the data model, and the event lifecycle.

## One-line shape

Kept is a Python program on a laptop that listens to Slack over a websocket,
asks Gemini to read messages, and tells Slack what to draw. The only non-Slack
pieces are Gemini (the AI) and a small SQLite file (Kept's private memory).

## Components, one job each

| File | Job |
| --- | --- |
| `backend/app.py` | The Bolt app. Receives Slack events and button clicks, routes them, wires everything together |
| `backend/config.py` | Reads secrets and settings from `.env`. The only place secrets are loaded |
| `backend/llm.py` | The single seam to Gemini. All AI calls go through here, so the provider is swappable in one file |
| `backend/extractor.py` | Given a message, asks the LLM "is this a promise? who? by when?" and returns structured data or nothing |
| `backend/store.py` | The SQLite promise store. Kept's private memory, so the scheduler knows what is due |
| `backend/ledger.py` | Renders the promises into the channel canvas (the Ledger) |
| `backend/blocks.py` | Builds the Block Kit cards (the confirm card, the nudge, the draft) |
| `backend/drafter.py` | Uses the LLM to write the delay message and the weekly update |
| `backend/recall.py` | Live search over Slack via the Real-Time Search API, for recall questions |
| `backend/scheduler.py` | Checks the store on a timer and fires deadline nudges |

All ten modules are built and live. `scheduler` also escalates a blown promise,
`drafter` also writes the weekly digest, and `app` also serves the personal surface
(my promises, edit, `kept` commands). The BUILDLOG status table tracks each feature.

## Data model

Kept stores only confirmed, structured promises. Never raw messages, never channel
history. Two tables in `kept.db`:

```
channels
  channel_id      TEXT PRIMARY KEY   Slack channel id
  channel_name    TEXT               for display in the ledger
  canvas_id       TEXT               the ledger canvas for this channel (null until first promise)

promises
  id              INTEGER PRIMARY KEY
  channel_id      TEXT               which channel (FK -> channels)
  owner_id        TEXT               Slack user id of who owes it
  owner_name      TEXT               display name
  description     TEXT               the deliverable, short
  recipient       TEXT               who it is promised to, nullable (only when named)
  due_date        TEXT               ISO date (YYYY-MM-DD), nullable
  due_time        TEXT               clock time HH:MM, nullable (only when a time was stated)
  status          TEXT               'open' or 'kept'
  source_permalink TEXT              link back to the source thread
  reschedule_count INTEGER           default 0
  nudged_at       TEXT               ISO timestamp, set when first nudged, cleared on reschedule
  escalated_at    TEXT               ISO timestamp, set when re-nudged past the deadline
  created_at      TEXT               ISO timestamp
  kept_at         TEXT               ISO timestamp, null until kept
```

Two more tables hold the in-flight cards, so a restart does not drop a confirmation or
draft that is waiting on a tap. They are transient by nature and small:

```
pending_confirmations   key (source message ts) -> a JSON promise awaiting Track
pending_drafts          pid (or digest:channel) -> a JSON drafted message awaiting Post
```

Derived, not stored: "overdue" is `status = 'open'` past the due date (or due time, when
set). Computing it keeps the store minimal and avoids stale flags.

## Event lifecycle

Detect and track:

```
message posted in a channel Kept is in
  -> app.py hears it (ignores bots, its own messages, trivial text)
  -> a `kept ...` command or @Kept mention? route to the command (see Commands below)
  -> extractor.py asks the LLM: promise? who? to whom? when (date and time)? confidence?
  -> below threshold: drop silently
  -> close-worded to an existing open promise with a new date? offer a reschedule card
  -> otherwise: app.py saves a pending confirmation and posts an ephemeral confirm card
  -> user taps Track (the button carries an opaque key, not the promise data)
  -> app.py pops the pending promise, writes it via store.py
  -> ledger.py rewrites the channel canvas
```

Track any message (the message action, for what auto-detect missed or someone else
said):

```
user hovers any message -> ... -> "Track as promise"
  -> app.py reads that one message's text and its author
  -> extractor.py pulls the promise (owner = who wrote it, not who tracked it)
  -> nothing found: ephemeral "no promise here", nothing stored
  -> found: app.py opens a modal with a date/time picker, prefilled from the extraction
  -> on submit: store.py writes it, ledger.py rewrites the canvas
```

The human choosing the message and confirming the date is the confirmation. It reads
only the hovered message, not the surrounding chat (see "said versus agreed" in
DECISIONS.md).

Nudge and escalate:

```
scheduler.py wakes on a timer, reads the clock in the workspace timezone
  -> store.py returns open promises due today or earlier, not yet nudged
  -> a timed promise waits until its time (minus any lead) before firing
  -> DM the owner a nudge card: Mark kept / Need more time
  -> Mark kept flips it; Need more time opens a date picker and reschedules
  -> reschedule -> drafter.py writes a delay message -> DM'd to the owner to send or post
  -> a promise already nudged and now past its deadline gets one sharper escalation DM
```

Recall:

```
user DMs Kept (or asks in the agent panel) "what did we promise about the deck?"
  -> app.py routes the DM: a command, or a recall question
  -> recall.py searches the question's topic words via the Real-Time Search API (live, no index)
  -> the LLM synthesises a short answer, citing only the messages it used
  -> app.py replies with the answer plus source permalinks
```

The agent-panel events do not deliver reliably in the sandbox, so the DM is the path
that works. Both route through the same recall, so only one answers a given message.

Commands and the personal surface:

```
`kept help` / `kept digest` / `kept stats` in a channel (or @Kept)  -> ephemeral reply
`my promises` in a DM (or `kept mine` in a channel)                 -> your open list, each row with
                                                                       Mark kept / Reschedule / Edit
Edit, on a row or the confirm card                                  -> a modal to fix wording, date, time
Kept added to a channel (member_joined_channel)                     -> posts a one-time welcome
```

## Key decisions and why

- Bolt for Python, so we do not hand-roll event routing or auth.
- Socket Mode, so no public URL or tunnel is needed to run on a laptop.
- SQLite is the source of truth for the scheduler; the canvas is the human-readable
  view. We do not parse the canvas back. This keeps nudges reliable and the store
  minimal, and lets us claim honestly: no raw Slack content stored outside Slack.
- One `llm.py` seam, so Gemini can be swapped for another provider in one place.
- Button payloads carry an opaque promise id or key, never the promise fields, so a
  tampered click cannot inject arbitrary data.
- In-flight confirmations and drafts persist in SQLite, so a restart does not drop a
  card waiting on a tap. Still structured, still no raw messages.
- Nudge timing runs against the workspace timezone (`config.TIMEZONE`), not the server
  clock, so "due 5pm" fires at 5pm where the team is.

See `assets/kept-architecture.png` for the visual map and the mockup for the UI target.
