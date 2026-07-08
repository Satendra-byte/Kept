# Kept, build log

Running record of what is built, changed, and decided. Newest entries at the top.
Feature status table first, then the dated log.

## Feature status

| Feature | Status | Notes |
| --- | --- | --- |
| Project scaffolding (docs, git, structure) | done | PRD, ARCHITECTURE, ENGINEERING, this log, manifest |
| config + secrets loading | todo | first code file |
| Slack app created + installed to sandbox | todo | from manifest.json |
| llm seam (Gemini) | todo | |
| commitment extractor | todo | with prompt-injection posture |
| promise store (sqlite) | todo | |
| confirm card + track flow | todo | ephemeral card, opaque id in button |
| ledger canvas | todo | canvas per channel |
| nudge scheduler | todo | |
| delay-message drafter | todo | |
| weekly update drafter | todo | should-have |
| recall (RTS) | todo | uses user token |
| agent panel wiring | todo | suggested prompts + Q and A |
| demo data + polish | todo | the sandbox story: Studio North, Fernhill |

## Log

### 7 Jul 2026 — project scaffolding

Set up the project bones before writing code:

- `manifest.json`: Slack app config, least-privilege scopes, Socket Mode, agent + message events.
- `PRD.md`: problem, users, scope (must/should/won't), success defined as the demo.
- `ARCHITECTURE.md`: component map, SQLite data model (channels + promises), event lifecycle, key decisions.
- `ENGINEERING.md`: right-sized security posture. Threat model, controls we implement, controls we deliberately skip and why, the prompt-injection posture, code and git standards.
- `.gitignore`: `.env` and local data never committed.
- `.env.example`, `requirements.txt`.
- Sandbox provisioned earlier: workspace "Kept" at kept-dev.enterprise.slack.com, event code SABC-7X2K-M9PL-4QFN, Slack AI Search confirmed enabled.

Next: `backend/config.py`, the secrets and settings loader.
