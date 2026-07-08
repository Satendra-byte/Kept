# Kept, house rules for this repo

Read this before working in the repo. Product and design context lives in
`PRD.md`, `ARCHITECTURE.md`, `ENGINEERING.md`, and `BUILDLOG.md`.

## Git

- Commits are authored by Satendra Tiwari only.
- NEVER add a `Co-Authored-By: Claude` trailer or any AI co-author trailer. This
  repo will be public.
- Conventional Commits: `feat:`, `fix:`, `docs:`, `refactor:`, `chore:`, `test:`.
- Never commit `.env` or any secret. If a secret is ever committed, rotate it.

## Code

- Ponytail default: the simplest thing that works. No speculative abstraction.
- ruff + black clean before any commit.
- Comment the why, not the what. No dead code.
- Parameterised SQL only, never string-built queries.
- Secrets are read only in `config.py`, from `.env`. Never hard-coded, never logged.

## Security posture (the two that matter)

- The LLM only classifies. It has no tools and takes no actions. Every outbound
  action (track, send, update) requires a human tap. Do not add an auto-action
  path without revisiting `ENGINEERING.md` section 4.
- Data minimisation: store only confirmed structured promises (description, owner,
  due date, source link). Never store raw messages or channel history.

## Writing style

- No em-dashes in any output, including docs and commit messages. Use commas,
  colons, or split the sentence.

## Keep the log alive

- When a feature is built, changed, or decided, update the feature table and add a
  dated entry in `BUILDLOG.md`.
