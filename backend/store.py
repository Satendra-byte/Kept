"""Kept's memory. A small SQLite store of confirmed promises so the scheduler knows
what is due. Holds only structured promises, never raw messages. Parameterised
queries only. One connection per call, so it is safe across the app and scheduler
threads.

It also persists in-flight confirmations and drafts (the cards waiting on a tap), so
a restart no longer drops them. Those are transient by nature, so a sweep clears
stale ones."""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

from backend import config


@contextmanager
def _db():
    conn = sqlite3.connect(config.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def init_db() -> None:
    with _db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS channels (
                channel_id   TEXT PRIMARY KEY,
                channel_name TEXT,
                canvas_id    TEXT
            );
            CREATE TABLE IF NOT EXISTS promises (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                channel_id       TEXT NOT NULL,
                owner_id         TEXT NOT NULL,
                owner_name       TEXT NOT NULL,
                description      TEXT NOT NULL,
                recipient        TEXT,
                due_date         TEXT,
                due_time         TEXT,
                status           TEXT NOT NULL DEFAULT 'open',
                source_permalink TEXT,
                reschedule_count INTEGER NOT NULL DEFAULT 0,
                nudged_at        TEXT,
                escalated_at     TEXT,
                created_at       TEXT NOT NULL,
                kept_at          TEXT
            );
            CREATE TABLE IF NOT EXISTS pending_confirmations (
                key        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS pending_drafts (
                pid        TEXT PRIMARY KEY,
                data       TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            """
        )
        # migrate dbs created before these columns existed (add each if missing)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(promises)").fetchall()]
        for col in ("recipient", "due_time", "escalated_at"):
            if col not in cols:
                c.execute(f"ALTER TABLE promises ADD COLUMN {col} TEXT")


# channels and their ledger canvas

def upsert_channel(channel_id: str, channel_name: str) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO channels (channel_id, channel_name) VALUES (?, ?) "
            "ON CONFLICT(channel_id) DO UPDATE SET channel_name = excluded.channel_name",
            (channel_id, channel_name),
        )


def set_canvas(channel_id: str, canvas_id: str) -> None:
    with _db() as c:
        c.execute("UPDATE channels SET canvas_id = ? WHERE channel_id = ?", (canvas_id, channel_id))


def get_canvas(channel_id: str) -> str | None:
    with _db() as c:
        row = c.execute("SELECT canvas_id FROM channels WHERE channel_id = ?", (channel_id,)).fetchone()
        return row["canvas_id"] if row else None


# promises

def add_promise(channel_id, owner_id, owner_name, description, due_date, source_permalink,
                recipient=None, due_time=None) -> int:
    with _db() as c:
        # skip an exact repeat: same owner, same wording, same date, still open here.
        # ponytail: exact match only, a reworded promise still makes a new row, fine.
        dupe = c.execute(
            "SELECT id FROM promises WHERE channel_id=? AND owner_id=? AND description=? "
            "AND due_date IS ? AND status='open'",
            (channel_id, owner_id, description, due_date),
        ).fetchone()
        if dupe:
            return dupe["id"]
        cur = c.execute(
            "INSERT INTO promises (channel_id, owner_id, owner_name, description, recipient, "
            "due_date, due_time, source_permalink, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (channel_id, owner_id, owner_name, description, recipient, due_date,
             due_time, source_permalink, _now()),
        )
        return cur.lastrowid


def update_promise(promise_id, description=None, due_date=None, due_time=None) -> None:
    """Edit a stored promise in place. Only the fields passed are changed; passing an
    empty string clears due_date/due_time (so 'no date' is expressible)."""
    sets, vals = [], []
    if description is not None:
        sets.append("description = ?"); vals.append(description)
    if due_date is not None:
        sets.append("due_date = ?"); vals.append(due_date or None)
    if due_time is not None:
        sets.append("due_time = ?"); vals.append(due_time or None)
    if not sets:
        return
    vals.append(promise_id)
    with _db() as c:
        c.execute(f"UPDATE promises SET {', '.join(sets)} WHERE id = ?", vals)


def get(promise_id: int) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT * FROM promises WHERE id = ?", (promise_id,)).fetchone()
        return dict(row) if row else None


def get_by_channel(channel_id: str) -> list[dict]:
    """All promises for a channel, open first then kept, for rendering the ledger."""
    with _db() as c:
        rows = c.execute(
            "SELECT * FROM promises WHERE channel_id = ? ORDER BY (status = 'open') DESC, due_date",
            (channel_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_due_for_nudge(cutoff_date: str) -> list[dict]:
    """Open promises due on or before cutoff that have not been nudged yet. This is the
    candidate set; the scheduler applies the time-of-day and lead-time cut before firing."""
    with _db() as c:
        rows = c.execute(
            "SELECT * FROM promises WHERE status = 'open' AND nudged_at IS NULL "
            "AND due_date IS NOT NULL AND due_date <= ?",
            (cutoff_date,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_overdue_for_escalation(cutoff_date: str) -> list[dict]:
    """Already-nudged open promises due on or before cutoff that have not been escalated.
    The scheduler confirms they are genuinely past due (with time) before re-nudging."""
    with _db() as c:
        rows = c.execute(
            "SELECT * FROM promises WHERE status = 'open' AND nudged_at IS NOT NULL "
            "AND escalated_at IS NULL AND due_date IS NOT NULL AND due_date <= ?",
            (cutoff_date,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_open_by_owner(owner_id: str, channel_id: str | None = None) -> list[dict]:
    """An owner's open promises, soonest due first, for the 'my promises' list. Scoped to
    one channel when given (used by reschedule-by-message), else across every channel."""
    q = "SELECT * FROM promises WHERE status = 'open' AND owner_id = ?"
    args = [owner_id]
    if channel_id is not None:
        q += " AND channel_id = ?"
        args.append(channel_id)
    q += " ORDER BY due_date IS NULL, due_date, due_time"
    with _db() as c:
        return [dict(r) for r in c.execute(q, args).fetchall()]


def get_stats(channel_id: str, today: str) -> list[dict]:
    """Per-owner kept-rate for a channel: how many promises each person kept versus
    slipped (open and past due). The demo's 'are we actually reliable' number."""
    with _db() as c:
        rows = c.execute(
            "SELECT owner_name, "
            "  SUM(status = 'kept') AS kept, "
            "  SUM(status = 'open' AND due_date IS NOT NULL AND due_date < ?) AS slipped, "
            "  SUM(status = 'open') AS open "
            "FROM promises WHERE channel_id = ? GROUP BY owner_name ORDER BY kept DESC",
            (today, channel_id),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_nudged(promise_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE promises SET nudged_at = ? WHERE id = ?", (_now(), promise_id))


def mark_escalated(promise_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE promises SET escalated_at = ? WHERE id = ?", (_now(), promise_id))


def mark_kept(promise_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE promises SET status = 'kept', kept_at = ? WHERE id = ?", (_now(), promise_id))


def reschedule(promise_id: int, new_due: str) -> None:
    with _db() as c:
        c.execute(
            "UPDATE promises SET due_date = ?, reschedule_count = reschedule_count + 1, "
            "nudged_at = NULL, escalated_at = NULL WHERE id = ?",
            (new_due, promise_id),
        )


# in-flight cards (confirmations and drafts) waiting on a human tap. Persisted so a
# restart does not drop them. The value is a small JSON blob; buttons still carry only
# the key, never the promise fields.

def put_pending(key: str, data: dict) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO pending_confirmations (key, data, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET data = excluded.data",
            (key, json.dumps(data), _now()),
        )


def pop_pending(key: str) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT data FROM pending_confirmations WHERE key = ?", (key,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM pending_confirmations WHERE key = ?", (key,))
        return json.loads(row["data"])


def get_pending(key: str) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT data FROM pending_confirmations WHERE key = ?", (key,)).fetchone()
        return json.loads(row["data"]) if row else None


def put_draft(pid: str, data: dict) -> None:
    with _db() as c:
        c.execute(
            "INSERT INTO pending_drafts (pid, data, created_at) VALUES (?, ?, ?) "
            "ON CONFLICT(pid) DO UPDATE SET data = excluded.data",
            (pid, json.dumps(data), _now()),
        )


def pop_draft(pid: str) -> dict | None:
    with _db() as c:
        row = c.execute("SELECT data FROM pending_drafts WHERE pid = ?", (pid,)).fetchone()
        if not row:
            return None
        c.execute("DELETE FROM pending_drafts WHERE pid = ?", (pid,))
        return json.loads(row["data"])


if __name__ == "__main__":
    # Self-check on a throwaway db. Needs .env populated (importing config requires it).
    import os
    import tempfile

    config.DB_PATH = os.path.join(tempfile.gettempdir(), "kept_selfcheck.db")
    init_db()

    pid = add_promise("C1", "U1", "Sachin", "revised deck", "2026-07-10", "http://x",
                      recipient="Priya", due_time="17:00")
    assert get(pid)["description"] == "revised deck"
    assert get(pid)["recipient"] == "Priya"
    assert get(pid)["due_time"] == "17:00"      # time-specific deadline stored
    assert get(pid)["status"] == "open"

    # an exact repeat while open returns the same row instead of duplicating
    assert add_promise("C1", "U1", "Sachin", "revised deck", "2026-07-10", "http://y") == pid

    # editing in place changes only the fields passed
    update_promise(pid, description="revised deck v2", due_time="18:30")
    assert get(pid)["description"] == "revised deck v2" and get(pid)["due_time"] == "18:30"

    assert [p["id"] for p in get_open_by_owner("U1")] == [pid]  # my-promises list

    assert len(get_due_for_nudge("2026-07-10")) == 1
    mark_nudged(pid)
    assert len(get_due_for_nudge("2026-07-10")) == 0  # never nudge the same promise twice

    # once nudged and past due it becomes an escalation candidate, once only
    assert [p["id"] for p in get_overdue_for_escalation("2026-07-10")] == [pid]
    mark_escalated(pid)
    assert get_overdue_for_escalation("2026-07-10") == []

    reschedule(pid, "2026-07-13")
    assert get(pid)["reschedule_count"] == 1
    assert get(pid)["escalated_at"] is None          # reschedule clears escalation too
    assert len(get_due_for_nudge("2026-07-13")) == 1  # reschedule makes it nudgeable again

    mark_kept(pid)
    assert get(pid)["status"] == "kept"

    # kept-rate stats: one kept, none slipped for Sachin
    stats = get_stats("C1", "2026-07-20")
    assert stats[0]["owner_name"] == "Sachin" and stats[0]["kept"] == 1 and stats[0]["slipped"] == 0

    # in-flight cards survive as rows and pop exactly once
    put_pending("ts1", {"description": "hold this"})
    assert get_pending("ts1")["description"] == "hold this"
    assert pop_pending("ts1")["description"] == "hold this"
    assert pop_pending("ts1") is None
    put_draft("9", {"text": "sorry", "channel_id": "C1"})
    assert pop_draft("9")["text"] == "sorry" and pop_draft("9") is None

    print("store self-check passed")
    os.remove(config.DB_PATH)
