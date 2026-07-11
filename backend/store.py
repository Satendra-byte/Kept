"""Kept's memory. A small SQLite store of confirmed promises so the scheduler knows
what is due. Holds only structured promises, never raw messages. Parameterised
queries only. One connection per call, so it is safe across the app and scheduler
threads."""
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
                due_date         TEXT,
                status           TEXT NOT NULL DEFAULT 'open',
                source_permalink TEXT,
                reschedule_count INTEGER NOT NULL DEFAULT 0,
                nudged_at        TEXT,
                created_at       TEXT NOT NULL,
                kept_at          TEXT
            );
            """
        )


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

def add_promise(channel_id, owner_id, owner_name, description, due_date, source_permalink) -> int:
    with _db() as c:
        cur = c.execute(
            "INSERT INTO promises (channel_id, owner_id, owner_name, description, due_date, "
            "source_permalink, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (channel_id, owner_id, owner_name, description, due_date, source_permalink, _now()),
        )
        return cur.lastrowid


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
    """Open promises due on or before cutoff that have not been nudged yet."""
    with _db() as c:
        rows = c.execute(
            "SELECT * FROM promises WHERE status = 'open' AND nudged_at IS NULL "
            "AND due_date IS NOT NULL AND due_date <= ?",
            (cutoff_date,),
        ).fetchall()
        return [dict(r) for r in rows]


def mark_nudged(promise_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE promises SET nudged_at = ? WHERE id = ?", (_now(), promise_id))


def mark_kept(promise_id: int) -> None:
    with _db() as c:
        c.execute("UPDATE promises SET status = 'kept', kept_at = ? WHERE id = ?", (_now(), promise_id))


def reschedule(promise_id: int, new_due: str) -> None:
    with _db() as c:
        c.execute(
            "UPDATE promises SET due_date = ?, reschedule_count = reschedule_count + 1, "
            "nudged_at = NULL WHERE id = ?",
            (new_due, promise_id),
        )


if __name__ == "__main__":
    # Self-check on a throwaway db. Needs .env populated (importing config requires it).
    import os
    import tempfile

    config.DB_PATH = os.path.join(tempfile.gettempdir(), "kept_selfcheck.db")
    init_db()

    pid = add_promise("C1", "U1", "Sachin", "revised deck", "2026-07-10", "http://x")
    assert get(pid)["description"] == "revised deck"
    assert get(pid)["status"] == "open"

    assert len(get_due_for_nudge("2026-07-10")) == 1
    mark_nudged(pid)
    assert len(get_due_for_nudge("2026-07-10")) == 0  # never nudge the same promise twice

    reschedule(pid, "2026-07-13")
    assert get(pid)["reschedule_count"] == 1
    assert len(get_due_for_nudge("2026-07-13")) == 1  # reschedule makes it nudgeable again

    mark_kept(pid)
    assert get(pid)["status"] == "kept"

    print("store self-check passed")
    os.remove(config.DB_PATH)
