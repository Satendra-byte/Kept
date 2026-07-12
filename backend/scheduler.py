"""The nudge timer. Sweeps the store for promises coming due and privately reminds
the owner, once each. Runs in a background thread alongside the Bolt app."""
import logging
from datetime import date, timedelta

from apscheduler.schedulers.background import BackgroundScheduler

from backend import blocks, config, store

log = logging.getLogger("kept.scheduler")


def check_and_nudge(client) -> None:
    """Remind the owner of every promise due within the lookahead we have not nudged."""
    lookahead_days = max(1, config.NUDGE_LOOKAHEAD_HOURS // 24)
    cutoff = (date.today() + timedelta(days=lookahead_days)).isoformat()
    due = store.get_due_for_nudge(cutoff)
    if due:
        log.info("nudge sweep: %d due", len(due))
    for p in due:
        try:
            _remind(client, p)
            store.mark_nudged(p["id"])
        except Exception:
            log.exception("nudge failed for promise %s", p["id"])


def _remind(client, p) -> None:
    """DM the owner if we can, else a private in-channel note. The DM needs im:write;
    the ephemeral fallback needs only chat:write, so a nudge lands either way while an
    im:write reinstall is pending."""
    try:
        dm = client.conversations_open(users=p["owner_id"])["channel"]["id"]
        client.chat_postMessage(channel=dm, blocks=blocks.nudge_blocks(p),
                                text="A promise is coming due")
    except Exception:
        client.chat_postEphemeral(channel=p["channel_id"], user=p["owner_id"],
                                  blocks=blocks.nudge_blocks(p), text="A promise is coming due")


def start(client) -> BackgroundScheduler:
    """Sweep on a timer. Returns the scheduler so the caller keeps a reference alive."""
    sched = BackgroundScheduler()
    sched.add_job(lambda: check_and_nudge(client), "interval",
                  seconds=config.NUDGE_INTERVAL_SECONDS, id="nudge_sweep")
    sched.start()
    log.info("nudge scheduler started, sweeping every %ds", config.NUDGE_INTERVAL_SECONDS)
    return sched
