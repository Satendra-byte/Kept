# Kept

The Slack agent that catches the promises your team makes to clients, and makes
sure they are kept.

Built for the Slack Agent Builder Challenge, 2026. New Slack Agent track.

## What it is

Kept lives in your client channels. It catches commitments as they are made,
keeps a Promise Ledger inside Slack as a canvas, nudges owners before deadlines,
and drafts the message when something slips. No separate app, no dashboard to
check. The tracking lives where the work already is.

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

## Repo map

| Path | What |
| --- | --- |
| `docs/PRD.md` | Product: problem, users, scope, what success looks like |
| `docs/ARCHITECTURE.md` | Technical design: components, data model, event flow |
| `docs/SECURITY.md` | Threat model, controls, and the prompt-injection posture |
| `BUILDLOG.md` | What is built and changed. Feature status table |
| `manifest.json` | Slack app configuration |
| `backend/` | The app |

## Team

Satendra Tiwari, with Sachin Tiwari and Debarghya Pal.
