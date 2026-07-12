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

Built so far: `app`, `config`, `llm`, `extractor`, `store`, `ledger`, `blocks`.
Planned: `scheduler`, `drafter`, `recall`. This doc describes the whole shape; the
BUILDLOG status table says what is live today.

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
  status          TEXT               'open' or 'kept'
  source_permalink TEXT              link back to the source thread
  reschedule_count INTEGER           default 0
  created_at      TEXT               ISO timestamp
  kept_at         TEXT               ISO timestamp, null until kept
```

Derived, not stored: "overdue" is `status = 'open' AND due_date < today`.
"at risk" is due within 24 hours and still open. Computing these keeps the store
minimal and avoids stale flags.

## Event lifecycle

Detect and track:

```
message posted in a channel Kept is in
  -> app.py hears it (ignores bots, its own messages, trivial text)
  -> extractor.py asks the LLM: promise? who? to whom? when? confidence?
  -> below threshold: drop silently
  -> above threshold: app.py posts an ephemeral confirm card (blocks.py)
  -> user taps Track (the button carries an opaque id, not the promise data)
  -> app.py loads the pending promise, writes it via store.py
  -> ledger.py rewrites the channel canvas
```

Track any message (the message action, for what auto-detect missed or someone else
said):

```
user hovers any message -> ... -> "Track as promise"
  -> app.py reads that one message's text and its author
  -> extractor.py pulls the promise (owner = who wrote it, not who tracked it)
  -> nothing found: ephemeral "no promise here", nothing stored
  -> found: store.py writes it, ledger.py rewrites the canvas
```

The human choosing the message is the confirmation, so there is no second card. It
reads only the hovered message, not the surrounding chat (see "said versus agreed" in
DECISIONS.md).
```

Nudge:

```
scheduler.py wakes on a timer
  -> store.py returns open promises due soon
  -> app.py DMs each owner a nudge card (blocks.py)
  -> "need more time" -> drafter.py writes a delay message -> posted for approval
```

Recall:

```
user asks Kept in the agent panel "what did we promise Fernhill?"
  -> recall.py calls the Real-Time Search API (live, no stored index)
  -> app.py replies in the panel with an answer plus source links
```

## Key decisions and why

- Bolt for Python, so we do not hand-roll event routing or auth.
- Socket Mode, so no public URL or tunnel is needed to run on a laptop.
- SQLite is the source of truth for the scheduler; the canvas is the human-readable
  view. We do not parse the canvas back. This keeps nudges reliable and the store
  minimal, and lets us claim honestly: no raw Slack content stored outside Slack.
- One `llm.py` seam, so Gemini can be swapped for another provider in one place.
- Button payloads carry an opaque promise id, never the promise fields, so a
  tampered click cannot inject arbitrary data.

See the flow diagram in chat and the mockup in `mockup/` for the visual target.
