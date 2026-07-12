"""Loads secrets and settings. The only place in the app that reads secrets."""
import os

from dotenv import load_dotenv

load_dotenv()


def _require(name: str) -> str:
    """Read a required secret from the environment, or fail with a clear message."""
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(
            f"Missing {name}. Copy .env.example to .env and fill it in."
        )
    return value


# Secrets: only ever read from .env, never hard-coded, never logged.
SLACK_BOT_TOKEN = _require("SLACK_BOT_TOKEN")
SLACK_APP_TOKEN = _require("SLACK_APP_TOKEN")
SLACK_USER_TOKEN = _require("SLACK_USER_TOKEN")
GEMINI_API_KEY = _require("GEMINI_API_KEY")

# Settings: not secret, so they live in code as the tuning knobs.
LLM_MODEL = "gemini-2.5-flash"
CONFIDENCE_THRESHOLD = 0.6   # drop extractions below this, silently
MIN_MESSAGE_CHARS = 15       # skip trivial messages before spending an LLM call
NUDGE_LOOKAHEAD_HOURS = 24   # nudge when a promise is due within this window
NUDGE_INTERVAL_SECONDS = 60  # how often the scheduler sweeps for due promises
DB_PATH = "kept.db"
