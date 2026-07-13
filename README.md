# Kept

The Slack agent that catches every promise your team makes, to a teammate or a
client, and makes sure it's kept.

Built for the Slack Agent Builder Challenge, 2026. New Slack Agent track.

## What it is

Kept lives in the channels where work happens. It catches commitments as they are
made, to teammates or clients, keeps a Promise Ledger inside Slack as a canvas,
nudges owners when a promise is due, and drafts the message when something slips.
No separate app, no dashboard to check. The tracking lives where the work already is.

## What it does

- Catches promises automatically and asks the owner to confirm with one tap. The model only ever suggests; nothing is tracked without a human tap.
- Keeps a Promise Ledger as a channel canvas: who owes what, to whom, by when, with a live Overdue section.
- Track any message from the `...` menu with *Track as promise*, with a date picker to confirm the deadline.
- Nudges the owner privately on the due day, or at the exact time for a timed promise ("by 5pm"), and escalates once when one blows past its deadline.
- Drafts the honest "running late" note when a promise slips, for a human to send.
- Answers *what did we promise?* live from the Real-Time Search API, with source links.
- `kept digest` drafts a weekly client update from the ledger; `kept stats` shows the kept-rate per person. DM `my promises` to settle yours.

## Using Kept

Once Kept is in a channel, you mostly just talk. Everything below is how you trigger each thing.

**In the channel**
- Make a promise: type `I'll send the report by Monday`. Kept spots it and offers to track it; one tap confirms.
- Give it a time: `I'll send the numbers today at 5pm`. Kept nudges you at 5pm, not before.
- Track any message (yours, a teammate's, a client's): hover it, click `...` (More actions), and choose *Track as promise* (under *More message shortcuts* if it is not listed directly), then confirm or adjust the date.
- `kept digest` drafts a weekly client update from the ledger.
- `kept stats` shows the kept-rate, who is keeping their promises.
- `kept help` lists everything.

**The ledger**
- Kept creates the Promise Ledger as a channel canvas the first time a promise is tracked (rename the tab to *Promises*). It shows who owes what, to whom, by when, with an Overdue section, and updates itself on every change.

**DM Kept directly**
- `my promises` lists your open ones, each with Mark kept, Reschedule, and Edit buttons.
- `what did we promise about the report?` answers live from the channel, with links to the source messages.

**On its own**
- Nudges the owner privately when a promise is due, and again, more sharply, if it blows past the deadline.
- When a promise slips, drafts the honest "running late" message for a human to send. Kept never sends anything itself.

## Quickstart

Prereqs: Python 3.11+, a Slack developer sandbox, a free Gemini API key.

1. Create the Slack app from `manifest.json` at api.slack.com/apps (From manifest),
   pick your sandbox workspace.
2. Enable the Agent feature, enable Socket Mode and create an app-level token,
   then install to the workspace.
3. Copy `.env.example` to `.env` and fill in the three Slack tokens and the Gemini key.
4. Install deps and run:

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python -m backend.app
```

5. In Slack, `/invite @Kept` to a channel, then make a promise like
   "I'll send the deck Friday" and watch the confirm card appear.

## Test

```bash
python -m pytest -q          # offline suite, mocked LLM and Slack
python -m backend.store      # per-module smoke checks (store, blocks, ledger are offline)
python -m backend.extractor  # extractor, drafter, recall hit the live LLM
```

## Evaluation

The commitment detector is measured against a hand-labeled set of 28 messages (clear
promises, questions, past-tense statements, vague intentions, and prompt injections).
Run it with `python -m eval.eval_extractor`.

| Metric | Result |
| --- | --- |
| Precision | 0.94 |
| Recall | 1.00 |
| F1 | 0.97 |
| Prompt injections refused | 3 / 3 |
| Due dates correct (caught promises) | 15 / 15 |
| Recipients correct (caught promises) | 4 / 4 |

It catches every real promise, resolves every date and recipient correctly, and refuses
every injection. The single false positive is a vague behavioral pledge with no
deliverable, the borderline case the one-tap confirm is there to absorb.

## Repo map

| Path | What |
| --- | --- |
| `docs/PRD.md` | Product: problem, users, scope, what success looks like |
| `docs/ARCHITECTURE.md` | Technical design: components, data model, event flow |
| `docs/SECURITY.md` | Threat model, controls, and the prompt-injection posture |
| `BUILDLOG.md` | What is built and changed. Feature status table |
| `manifest.json` | Slack app configuration |
| `backend/` | The app |
| `tests/` | Offline test suite (mocked LLM and Slack) |

## Team

Satendra Tiwari, with Sachin Tiwari and Debarghya Pal.
