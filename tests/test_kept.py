"""Kept's test suite: the logic that would quietly break a demo if it regressed, run
offline. The LLM and Slack are mocked, so nothing here needs network or tokens beyond
what importing config already loads. Run: python -m pytest -q"""
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend import app, blocks, config, extractor, ledger, llm, recall, scheduler, store


# ---- fixtures --------------------------------------------------------------------

@pytest.fixture
def db(tmp_path, monkeypatch):
    """A throwaway SQLite db for the test, wired in via config.DB_PATH."""
    monkeypatch.setattr(config, "DB_PATH", str(tmp_path / "t.db"))
    store.init_db()
    return config.DB_PATH


class FakeClient:
    """The slivers of the Slack client the code under test calls, recording sends."""
    def __init__(self):
        self.posts = []
        self.ephemerals = []

    def conversations_open(self, users):
        return {"channel": {"id": "D1"}}

    def chat_postMessage(self, channel, text=None, blocks=None):
        self.posts.append({"channel": channel, "text": text, "blocks": blocks})
        return {"ok": True}

    def chat_postEphemeral(self, channel, user, text=None, blocks=None):
        self.ephemerals.append({"channel": channel, "user": user, "text": text})
        return {"ok": True}

    def users_info(self, user):
        return {"user": {"profile": {"display_name": "Priya"}, "real_name": "Priya Shah"}}


def _dt(y, m, d, hh, mm):
    return datetime(y, m, d, hh, mm, tzinfo=ZoneInfo(config.TIMEZONE))


# ---- store -----------------------------------------------------------------------

def test_store_lifecycle_and_time(db):
    pid = store.add_promise("C1", "U1", "Sam", "send deck", "2026-07-10", "http://x",
                            recipient="Priya", due_time="17:00")
    p = store.get(pid)
    assert p["due_time"] == "17:00" and p["recipient"] == "Priya" and p["status"] == "open"
    # exact repeat while open does not duplicate
    assert store.add_promise("C1", "U1", "Sam", "send deck", "2026-07-10", "http://y") == pid


def test_store_update_only_touches_passed_fields(db):
    pid = store.add_promise("C1", "U1", "Sam", "send deck", "2026-07-10", None, due_time="17:00")
    store.update_promise(pid, description="send deck v2")
    p = store.get(pid)
    assert p["description"] == "send deck v2" and p["due_time"] == "17:00"  # time untouched
    store.update_promise(pid, due_date="", due_time="")                    # empty string clears
    p = store.get(pid)
    assert p["due_date"] is None and p["due_time"] is None


def test_store_nudge_and_escalation_candidates(db):
    pid = store.add_promise("C1", "U1", "Sam", "send deck", "2026-07-10", None)
    assert [x["id"] for x in store.get_due_for_nudge("2026-07-10")] == [pid]
    store.mark_nudged(pid)
    assert store.get_due_for_nudge("2026-07-10") == []            # nudged only once
    assert [x["id"] for x in store.get_overdue_for_escalation("2026-07-10")] == [pid]
    store.mark_escalated(pid)
    assert store.get_overdue_for_escalation("2026-07-10") == []   # escalated only once


def test_store_reschedule_clears_nudge_and_escalation(db):
    pid = store.add_promise("C1", "U1", "Sam", "send deck", "2026-07-10", None)
    store.mark_nudged(pid); store.mark_escalated(pid)
    store.reschedule(pid, "2026-07-13")
    p = store.get(pid)
    assert p["nudged_at"] is None and p["escalated_at"] is None and p["reschedule_count"] == 1


def test_store_stats_and_my_promises(db):
    kept = store.add_promise("C1", "U1", "Sam", "a", "2026-07-01", None)
    store.mark_kept(kept)
    store.add_promise("C1", "U1", "Sam", "b", "2026-07-01", None)   # open and long overdue
    rows = store.get_stats("C1", "2026-07-20")
    r = next(x for x in rows if x["owner_name"] == "Sam")
    assert r["kept"] == 1 and r["slipped"] == 1
    assert len(store.get_open_by_owner("U1")) == 1                  # only the open one


def test_store_pending_roundtrip(db):
    store.put_pending("ts1", {"description": "hold"})
    assert store.get_pending("ts1")["description"] == "hold"
    assert store.pop_pending("ts1")["description"] == "hold"
    assert store.pop_pending("ts1") is None                        # popped once
    store.put_draft("9", {"text": "sorry"})
    assert store.pop_draft("9")["text"] == "sorry" and store.pop_draft("9") is None


# ---- extractor -------------------------------------------------------------------

def test_date_reference_resolves_weekdays():
    ref = extractor._date_reference(date(2026, 7, 11))  # a Saturday
    assert "Monday: 2026-07-13" in ref and "today: 2026-07-11 (Saturday)" in ref


def test_extract_drops_non_commitment(monkeypatch):
    monkeypatch.setattr(llm, "generate_json",
                        lambda s, p: {"is_commitment": False, "confidence": 0.9})
    assert extractor.extract("where are we on the deck?", "Sam", "2026-07-09") is None


def test_extract_drops_low_confidence(monkeypatch):
    monkeypatch.setattr(llm, "generate_json",
                        lambda s, p: {"is_commitment": True, "description": "x", "confidence": 0.3})
    assert extractor.extract("maybe I'll look at it", "Sam", "2026-07-09") is None


def test_extract_returns_fields_incl_time(monkeypatch):
    monkeypatch.setattr(llm, "generate_json", lambda s, p: {
        "is_commitment": True, "description": "send deck", "recipient": "Priya",
        "due_date": "2026-07-10", "due_time": "17:00", "confidence": 0.8})
    got = extractor.extract("Priya, deck by 5pm Friday", "Sam", "2026-07-09")
    assert got["due_time"] == "17:00" and got["recipient"] == "Priya"


# ---- ledger ----------------------------------------------------------------------

def test_ledger_buckets_and_time_and_escaping():
    rows = [
        {"status": "open", "description": "a | b split", "owner_name": "Sam", "recipient": "Priya",
         "due_date": "2026-07-10", "due_time": "17:00", "source_permalink": "http://x", "kept_at": None},
        {"status": "open", "description": "later", "owner_name": "Sam", "recipient": None,
         "due_date": "2026-07-20", "due_time": None, "source_permalink": None, "kept_at": None},
        {"status": "kept", "description": "done", "owner_name": "Sam", "recipient": None,
         "due_date": "2026-07-01", "due_time": None, "source_permalink": None,
         "kept_at": "2026-07-02T09:00:00+00:00"},
    ]
    md = ledger.render(rows, today="2026-07-15")
    assert "## Overdue (1)" in md and "## Open (1)" in md and "## Kept (1)" in md
    assert "2026-07-10 17:00" in md            # timed deadline shows the clock time
    assert "a \\| b split" in md               # pipe escaped so the table survives
    assert "2026-07-02" in md and "T09" not in md
    assert "Nothing open" in ledger.render([])


# ---- blocks ----------------------------------------------------------------------

def test_blocks_confirm_shows_time_and_carries_only_id():
    p = {"id": 7, "description": "deck", "owner_name": "Sam", "recipient": "Priya",
         "due_date": "2026-07-10", "due_time": "17:00"}
    built = blocks.confirm_blocks(p)
    ctx = [b for b in built if b["type"] == "context"][0]["elements"][0]["text"]
    assert "2026-07-10 17:00" in ctx and "Priya" in ctx
    acts = [b for b in built if b["type"] == "actions"][0]["elements"]
    assert all(a["value"] == "7" for a in acts)


def test_blocks_nudge_overdue_wording():
    p = {"id": 1, "description": "deck", "due_date": "2026-07-10", "due_time": None}
    assert "overdue" in blocks.nudge_blocks(p, overdue=True)[0]["text"]["text"].lower()


def test_blocks_my_promises_empty_and_populated():
    assert blocks.my_promises_blocks([])[0]["text"]["text"].endswith("All clear.")
    p = {"id": 3, "description": "deck", "recipient": None, "due_date": "2026-07-10", "due_time": None}
    acts = [b for b in blocks.my_promises_blocks([p]) if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in acts] == ["mark_kept", "need_time", "edit_tracked"]


def test_blocks_edit_modal_prefills():
    em = blocks.edit_modal(7, "deck", "2026-07-10", "17:00")
    assert em["blocks"][1]["element"]["initial_date"] == "2026-07-10"
    assert em["blocks"][2]["element"]["initial_time"] == "17:00"


# ---- recall ----------------------------------------------------------------------

def test_recall_terms_strip_filler():
    assert recall._terms("what did we promise about the file?") == "file"


def test_recall_no_hits(monkeypatch):
    monkeypatch.setattr(recall._search, "api_call",
                        lambda *a, **k: SimpleNamespace(data={"results": {"messages": []}}))
    assert "could not find" in recall.answer("what did we promise about x?").lower()


def test_recall_cites_only_referenced_sources(monkeypatch):
    msgs = [{"author_name": "Sam", "content": "deck Friday", "permalink": "http://1"},
            {"author_name": "Ann", "content": "call Monday", "permalink": "http://2"}]
    monkeypatch.setattr(recall._search, "api_call",
                        lambda *a, **k: SimpleNamespace(data={"results": {"messages": msgs}}))
    monkeypatch.setattr(llm, "generate_text", lambda s, p: "Sam will send the deck Friday [1].")
    out = recall.answer("what about the deck?")
    assert "http://1" in out and "http://2" not in out   # only the cited source is shown


# ---- scheduler timing ------------------------------------------------------------

def test_scheduler_timed_promise_waits_for_its_time(db, monkeypatch):
    pid = store.add_promise("C1", "U1", "Sam", "deck", "2026-07-12", None, due_time="17:00")
    client = FakeClient()
    monkeypatch.setattr(scheduler, "_now_local", lambda: _dt(2026, 7, 12, 9, 0))
    scheduler.check_and_nudge(client)
    assert client.posts == [] and store.get(pid)["nudged_at"] is None   # 9am, not yet 5pm

    monkeypatch.setattr(scheduler, "_now_local", lambda: _dt(2026, 7, 12, 17, 1))
    scheduler.check_and_nudge(client)
    assert len(client.posts) == 1 and store.get(pid)["nudged_at"] is not None


def test_scheduler_lead_time_nudges_early(db, monkeypatch):
    store.add_promise("C1", "U1", "Sam", "deck", "2026-07-12", None, due_time="17:00")
    monkeypatch.setattr(config, "NUDGE_LEAD_MINUTES", 120)   # two hours early
    client = FakeClient()
    monkeypatch.setattr(scheduler, "_now_local", lambda: _dt(2026, 7, 12, 15, 5))
    scheduler.check_and_nudge(client)
    assert len(client.posts) == 1                            # 3:05pm is within the 2h lead


def test_scheduler_date_only_nudges_on_the_day(db, monkeypatch):
    store.add_promise("C1", "U1", "Sam", "deck", "2026-07-12", None)
    client = FakeClient()
    monkeypatch.setattr(scheduler, "_now_local", lambda: _dt(2026, 7, 12, 8, 0))
    scheduler.check_and_nudge(client)
    assert len(client.posts) == 1                            # date-only fires any time that day


def test_scheduler_escalates_once_when_overdue(db, monkeypatch):
    pid = store.add_promise("C1", "U1", "Sam", "deck", "2026-07-12", None, due_time="17:00")
    store.mark_nudged(pid)                                   # already nudged earlier
    client = FakeClient()
    monkeypatch.setattr(scheduler, "_now_local", lambda: _dt(2026, 7, 12, 16, 0))
    scheduler.check_and_nudge(client)
    assert store.get(pid)["escalated_at"] is None            # 4pm, not overdue yet

    monkeypatch.setattr(scheduler, "_now_local", lambda: _dt(2026, 7, 12, 18, 0))
    scheduler.check_and_nudge(client)
    assert store.get(pid)["escalated_at"] is not None
    esc = [pp for pp in client.posts if "overdue" in (pp["text"] or "").lower()]
    assert len(esc) == 1


# ---- app: command parsing and helpers --------------------------------------------

def test_channel_command_needs_prefix(monkeypatch):
    monkeypatch.setattr(app, "BOT_USER_ID", "BKEPT")
    assert app._channel_command("kept digest") == "digest"
    assert app._channel_command("<@BKEPT> stats") == "stats"
    assert app._channel_command("just chatting about the digest") is None   # no prefix, not a command


def test_dm_command_and_smalltalk():
    assert app._dm_command("my promises") == "mine"
    assert app._dm_command("what did we promise about the deck?") is None   # a real question -> recall
    assert app._is_smalltalk("hi") and app._is_smalltalk("thanks")
    assert not app._is_smalltalk("what did we promise about the launch")


def test_resolve_recipient_turns_mention_into_name():
    c = FakeClient()
    assert app._resolve_recipient(c, "<@U12345678>") == "Priya"   # mention resolved
    assert app._resolve_recipient(c, "Sam") == "Sam"              # plain name kept
    assert app._resolve_recipient(c, None) is None


def test_reschedule_match_only_on_close_wording_and_new_date(db):
    store.add_promise("C1", "U1", "Sam", "send the deck", "2026-07-12", None)
    same = {"description": "send the deck", "due_date": "2026-07-12"}
    moved = {"description": "send the deck", "due_date": "2026-07-14"}
    other = {"description": "call the client", "due_date": "2026-07-14"}
    assert app._reschedule_match("U1", "C1", same) is None        # same date, not a reschedule
    assert app._reschedule_match("U1", "C1", moved) is not None   # close wording, new date
    assert app._reschedule_match("U1", "C1", other) is None       # unrelated wording


def test_stats_text_formats_kept_rate(db):
    k = store.add_promise("C1", "U1", "Sam", "a", "2026-07-01", None)
    store.mark_kept(k)
    store.add_promise("C1", "U1", "Sam", "b", "2026-07-01", None)  # slipped
    out = app._stats_text("C1")
    assert "Sam" in out and "kept-rate 50%" in out
