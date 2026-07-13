"""The nudge timer. Sweeps the store for promises coming due and privately reminds
the owner, once each, then escalates the ones that blew past their deadline. Runs in a
background thread alongside the Bolt app. All timing is against the workspace timezone
(config.TIMEZONE), not the server clock, so 'due 5pm' means 5pm where the team is."""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from apscheduler.schedulers.background import BackgroundScheduler

from backend import blocks, config, store

log = logging.getLogger("kept.scheduler")


def _now_local() -> datetime:
    return datetime.now(ZoneInfo(config.TIMEZONE))


def _due_dt(p) -> datetime:
    """The moment a promise is due, in the workspace timezone. A promise with no clock
    time is treated as due at the start of its day (so it nudges any time that day)."""
    t = p["due_time"] or "00:00"
    return datetime.fromisoformat(f"{p['due_date']}T{t}").replace(tzinfo=ZoneInfo(config.TIMEZONE))


def check_and_nudge(client) -> None:
    """Remind the owner of every promise due now (or overdue) that we have not nudged,
    then escalate ones already nudged that are now genuinely past their deadline.

    Nudging on the due day, not before, is deliberate: a reschedule to a later day then
    waits for that day. A timed promise waits for its time, minus the lead."""
    now = _now_local()
    today = now.date().isoformat()
    lead = timedelta(minutes=config.NUDGE_LEAD_MINUTES)

    due = store.get_due_for_nudge(today)
    nudged_now = set()
    for p in due:
        # ponytail: lead only shifts within the due day; a day-early lead is not supported.
        if p["due_time"] and now < _due_dt(p) - lead:
            continue                       # a timed promise not yet at (its time minus lead)
        try:
            _remind(client, p)
            store.mark_nudged(p["id"])
            nudged_now.add(p["id"])
        except Exception:
            log.exception("nudge failed for promise %s", p["id"])

    for p in store.get_overdue_for_escalation(today):
        if p["id"] in nudged_now:
            continue                       # just nudged this sweep, do not also escalate it now
        # a timed promise is overdue past its time; a date-only one only once its day passed
        overdue = now >= _due_dt(p) if p["due_time"] else today > p["due_date"]
        if not overdue:
            continue
        try:
            _remind(client, p, overdue=True)
            store.mark_escalated(p["id"])
        except Exception:
            log.exception("escalation failed for promise %s", p["id"])


def _remind(client, p, overdue: bool = False) -> None:
    """DM the owner if we can, else a private in-channel note. The DM needs im:write;
    the ephemeral fallback needs only chat:write, so a nudge lands either way."""
    blks = blocks.nudge_blocks(p, overdue=overdue)
    text = "A promise is overdue" if overdue else "A promise is coming due"
    try:
        dm = client.conversations_open(users=p["owner_id"])["channel"]["id"]
        client.chat_postMessage(channel=dm, blocks=blks, text=text)
    except Exception:
        client.chat_postEphemeral(channel=p["channel_id"], user=p["owner_id"], blocks=blks, text=text)


def start(client) -> BackgroundScheduler:
    """Sweep on a timer. Returns the scheduler so the caller keeps a reference alive."""
    sched = BackgroundScheduler()
    sched.add_job(lambda: check_and_nudge(client), "interval",
                  seconds=config.NUDGE_INTERVAL_SECONDS, id="nudge_sweep")
    sched.start()
    log.info("nudge scheduler started, sweeping every %ds (tz %s)",
             config.NUDGE_INTERVAL_SECONDS, config.TIMEZONE)
    return sched
