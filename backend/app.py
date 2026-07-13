"""The Kept app. Hears messages, runs the extractor, drives the confirm flow, and
answers questions. Socket Mode, so no public URL is needed. Run: python -m backend.app

In-flight cards (confirmations, drafts) live in the store, not memory, so a restart
does not drop them. Buttons carry only an opaque key, never promise fields, so a
tampered click cannot inject a promise."""
import logging
import re
from datetime import date

from slack_bolt import App, Assistant
from slack_bolt.adapter.socket_mode import SocketModeHandler

from backend import blocks, config, drafter, extractor, ledger, recall, scheduler, store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kept")

# token_verification off: we validate the token ourselves via auth.test in __main__, and
# skipping the init-time network call keeps the module importable offline for the tests.
app = App(token=config.SLACK_BOT_TOKEN, token_verification_enabled=False)

# Set once at startup from auth.test. Used to spot the bot's own channel joins and to
# strip a leading @Kept mention off a command.
BOT_USER_ID: str | None = None

GREETINGS = {"hi", "hey", "hello", "yo", "sup", "gm", "hiya", "thanks", "thank you",
             "ok", "okay", "cool", "nice", "great"}

HELP = (
    "*Here is what I can do:*\n"
    "• Catch promises as they are made, to a teammate or a client, and ask you to confirm with one tap. "
    "I read a time too, so _by 5pm_ nudges at 5pm, not just on the day.\n"
    "• Track any message from its `...` menu with *Track as promise*, for one I missed or someone else made.\n"
    "• Keep the *Promises* canvas up to date, and DM me *my promises* to mark kept, reschedule, or edit yours.\n"
    "• Answer *what did we promise about X?* live from the channel, with links to the source.\n"
    "• *kept digest* drafts a weekly client update; *kept stats* shows the kept-rate per person.\n"
    "• On my own: nudge the owner when a promise is due, escalate if it slips, and draft the honest heads-up to send."
)


# ---- message routing -------------------------------------------------------------

@app.event("message")
def on_message(event, client):
    # never bots, our own, edits or joins
    if event.get("bot_id") or event.get("subtype"):
        return
    ctype = event.get("channel_type")
    if ctype == "im":
        _on_dm(event, client)
        return
    if ctype not in ("channel", "group"):
        return

    text = event.get("text", "")
    cmd = _channel_command(text)
    if cmd:
        _run_channel_command(client, event, cmd)
        return
    if len(text) < config.MIN_MESSAGE_CHARS:
        return
    _detect_promise(client, event, text)


def _on_dm(event, client):
    """A DM to Kept: a command (my promises / help / digest-or-stats hint) or a recall
    question. Greetings and one-word noise get help, not a wasted search. This is the
    only recall path for DMs; the agent panel handles assistant threads, a separate
    surface, so the two never answer the same message."""
    text = event.get("text", "").strip()
    channel, user = event["channel"], event["user"]
    if not text:
        return
    cmd = _dm_command(text)
    log.info("DM to Kept: cmd=%s text=%r", cmd, text[:60])
    try:
        if cmd == "mine":
            client.chat_postMessage(channel=channel, text="Your open promises",
                                    blocks=blocks.my_promises_blocks(store.get_open_by_owner(user)))
        elif cmd in ("digest", "stats"):
            client.chat_postMessage(channel=channel,
                                    text=f"Type `kept {cmd}` in the channel you want it for, so I know which one.")
        elif cmd == "help" or _is_smalltalk(text):
            client.chat_postMessage(channel=channel, text=HELP)
        else:
            client.chat_postMessage(channel=channel, text=recall.answer(text))
    except Exception:
        log.exception("DM handling failed")
        client.chat_postMessage(channel=channel,
                                text="I hit a snag just now, try me again in a moment.")


def _run_channel_command(client, event, cmd):
    channel, user = event["channel"], event["user"]
    if cmd == "mine":
        _ephemeral(client, channel, user, "Your open promises",
                   blocks.my_promises_blocks(store.get_open_by_owner(user, channel)))
    elif cmd == "stats":
        _ephemeral(client, channel, user, _stats_text(channel))
    elif cmd == "help":
        _ephemeral(client, channel, user, HELP)
    elif cmd == "digest":
        promises = store.get_by_channel(channel)
        kept = [p for p in promises if p["status"] == "kept"]
        open_ = [p for p in promises if p["status"] == "open"]
        if not kept and not open_:
            _ephemeral(client, channel, user, "Nothing tracked here yet, so there is nothing to summarise.")
            return
        key = f"digest:{channel}"
        text = drafter.draft_digest(kept, open_)
        store.put_draft(key, {"text": text, "channel_id": channel})
        _ephemeral(client, channel, user, "Weekly update draft", blocks.digest_blocks(key, text))


def _detect_promise(client, event, text):
    channel, user = event["channel"], event["user"]
    author = _display_name(client, user)
    found = extractor.extract(text, author, date.today().isoformat())
    if not found:
        return

    key = event["ts"]
    data = {
        "channel_id": channel, "owner_id": user, "owner_name": author,
        "description": found["description"], "recipient": _resolve_recipient(client, found.get("recipient")),
        "due_date": found["due_date"], "due_time": found.get("due_time"), "source_ts": event["ts"],
    }

    match = _reschedule_match(user, channel, found)
    if match:
        data["reschedule_of"] = match["id"]
        store.put_pending(key, data)
        _ephemeral(client, channel, user, "Is this an update?",
                   blocks.reschedule_match_blocks(key, match["description"],
                                                  _when(found["due_date"], found.get("due_time"))))
        return

    store.put_pending(key, data)
    _ephemeral(client, channel, user, "Track this commitment?",
               blocks.confirm_blocks({"id": key, **data}))


# ---- confirm / track -------------------------------------------------------------

@app.action("track_promise")
@app.action("track_new")
def on_track(ack, body, client, respond):
    ack()
    _do_track(store.pop_pending(body["actions"][0]["value"]), client, respond)


def _do_track(data, client, respond):
    if not data:
        respond(replace_original=True, text="That confirmation expired. Say it again if you still want it tracked.")
        return
    store.upsert_channel(data["channel_id"], _channel_name(client, data["channel_id"]))
    store.add_promise(
        data["channel_id"], data["owner_id"], data["owner_name"], data["description"],
        data["due_date"], _permalink(client, data["channel_id"], data["source_ts"]),
        recipient=data.get("recipient"), due_time=data.get("due_time"),
    )
    _sync(client, data["channel_id"])
    respond(replace_original=True,
            text=f'Tracked. "{data["description"]}" is in the ledger, due {_when(data["due_date"], data.get("due_time"))}.')


@app.action("reschedule_match")
def on_reschedule_match(ack, body, client, respond):
    ack()
    data = store.pop_pending(body["actions"][0]["value"])
    if not data or "reschedule_of" not in data:
        respond(replace_original=True, text="That expired. Say it again if you still want it changed.")
        return
    pid, new_due = data["reschedule_of"], data["due_date"]
    store.reschedule(pid, new_due)
    if data.get("due_time") is not None:
        store.update_promise(pid, due_time=data["due_time"])
    p = store.get(pid)
    if p:
        _sync(client, p["channel_id"])
        _offer_delay_draft(client, p, new_due)
    respond(replace_original=True, text=f'Updated. "{data["description"]}" now due {_when(new_due, data.get("due_time"))}.')


@app.action("ignore_promise")
def on_ignore(ack, body, respond):
    ack()
    store.pop_pending(body["actions"][0]["value"])
    respond(replace_original=True, text="Okay, leaving that one alone.")


@app.action("edit_promise")
def on_edit(ack, body, client, respond):
    """Edit on the confirm card: open the modal prefilled from the pending promise, so the
    date or wording can be fixed before it is tracked."""
    ack()
    key = body["actions"][0]["value"]
    data = store.get_pending(key)
    if not data:
        respond(replace_original=True, text="That one expired. Say it again to track it.")
        return
    client.views_open(trigger_id=body["trigger_id"],
                      view=blocks.track_modal(key, data["description"], data["due_date"], data.get("due_time")))


@app.view("track_submit")
def on_track_submit(ack, body, view, client):
    """The message-action and confirm-card Edit both land here: track the pending promise
    with whatever date, time, and wording the human left in the modal."""
    ack()
    key = view["private_metadata"]
    data = store.pop_pending(key)
    if not data:
        return
    desc, due_date, due_time = _modal_values(view)
    store.upsert_channel(data["channel_id"], _channel_name(client, data["channel_id"]))
    store.add_promise(
        data["channel_id"], data["owner_id"], data["owner_name"], desc or data["description"],
        due_date, _permalink(client, data["channel_id"], data["source_ts"]),
        recipient=data.get("recipient"), due_time=due_time,
    )
    _sync(client, data["channel_id"])
    _ephemeral(client, data["channel_id"], body["user"]["id"],
               f'Tracked. "{desc or data["description"]}" is in the ledger, due {_when(due_date, due_time)}.')


# ---- message action: track any message, with a date picker -----------------------

@app.shortcut("track_message")
def on_track_message(ack, shortcut, client):
    """Track any message the user picks. Opens the date picker so the human confirms or
    adjusts the deadline before it is tracked, rather than tracking blind."""
    ack()
    channel_id = shortcut["channel"]["id"]
    msg = shortcut["message"]
    author_id = msg.get("user") or shortcut["user"]["id"]  # owner is who made it, else who tracked it
    author = _display_name(client, author_id)

    found = extractor.extract(msg.get("text", ""), author, date.today().isoformat())
    if not found:
        client.chat_postEphemeral(channel=channel_id, user=shortcut["user"]["id"],
                                  text="I couldn't find a promise in that message, so I left it alone.")
        return
    key = msg["ts"]
    store.put_pending(key, {
        "channel_id": channel_id, "owner_id": author_id, "owner_name": author,
        "description": found["description"], "recipient": _resolve_recipient(client, found.get("recipient")),
        "due_date": found["due_date"], "due_time": found.get("due_time"), "source_ts": msg["ts"],
    })
    client.views_open(trigger_id=shortcut["trigger_id"],
                      view=blocks.track_modal(key, found["description"], found["due_date"], found.get("due_time")))


# ---- edit an already-tracked promise ---------------------------------------------

@app.action("edit_tracked")
def on_edit_tracked(ack, body, client):
    ack()
    p = store.get(int(body["actions"][0]["value"]))
    if p:
        client.views_open(trigger_id=body["trigger_id"],
                          view=blocks.edit_modal(p["id"], p["description"], p["due_date"], p.get("due_time")))


@app.view("edit_submit")
def on_edit_submit(ack, view, client):
    ack()
    pid = int(view["private_metadata"])
    desc, due_date, due_time = _modal_values(view)
    store.update_promise(pid, description=desc, due_date=due_date or "", due_time=due_time or "")
    p = store.get(pid)
    if p:
        _sync(client, p["channel_id"])


# ---- nudges: mark kept, reschedule -----------------------------------------------

@app.action("mark_kept")
def on_mark_kept(ack, body, client, respond):
    ack()
    pid = int(body["actions"][0]["value"])
    store.mark_kept(pid)
    p = store.get(pid)
    if p:
        _sync(client, p["channel_id"])
    respond(replace_original=True, text="Marked as kept. Nice work.")


@app.action("need_time")
def on_need_time(ack, body, client):
    ack()
    client.views_open(trigger_id=body["trigger_id"], view=blocks.reschedule_modal(body["actions"][0]["value"]))


@app.view("reschedule_submit")
def on_reschedule(ack, view, client):
    ack()
    pid = int(view["private_metadata"])
    new_due = view["state"]["values"]["new_due"]["date"]["selected_date"]
    store.reschedule(pid, new_due)
    p = store.get(pid)
    if not p:
        return
    _sync(client, p["channel_id"])
    _offer_delay_draft(client, p, new_due)


# ---- delay drafts and the weekly digest ------------------------------------------

def _offer_delay_draft(client, p, new_due):
    """DM the owner a drafted client heads-up about the slip, for them to send or post."""
    try:
        text = drafter.draft_delay(p["description"], new_due, p.get("recipient"))
        store.put_draft(str(p["id"]), {"text": text, "channel_id": p["channel_id"]})
        dm = client.conversations_open(users=p["owner_id"])["channel"]["id"]
        client.chat_postMessage(channel=dm, blocks=blocks.draft_blocks(str(p["id"]), text, p.get("recipient")),
                                text="A heads-up you can send the client")
    except Exception:
        log.exception("draft delay failed")


@app.action("post_draft")
def on_post_draft(ack, body, client, respond):
    ack()
    d = store.pop_draft(body["actions"][0]["value"])
    if not d:
        respond(replace_original=True, text="That draft expired. Reschedule again for a fresh one.")
        return
    client.chat_postMessage(channel=d["channel_id"], text=d["text"])
    respond(replace_original=True, text="Posted to the channel.")


@app.action("post_digest")
def on_post_digest(ack, body, client, respond):
    ack()
    d = store.pop_draft(body["actions"][0]["value"])
    if not d:
        respond(replace_original=True, text="That draft expired. Run `kept digest` again for a fresh one.")
        return
    client.chat_postMessage(channel=d["channel_id"], text=d["text"])
    respond(replace_original=True, text="Posted the weekly update to the channel.")


@app.action("dismiss_draft")
def on_dismiss_draft(ack, body, respond):
    ack()
    store.pop_draft(body["actions"][0]["value"])
    respond(replace_original=True, text="Okay, not sending it.")


# ---- onboarding: welcome when added to a channel ---------------------------------

@app.event("member_joined_channel")
def on_member_joined(event, client):
    """When Kept itself is added to a channel, introduce itself once. Needs the
    member_joined_channel event in the manifest (reinstall to activate)."""
    if event.get("user") != BOT_USER_ID:
        return
    try:
        client.chat_postMessage(
            channel=event["channel"],
            text=("Hi, I'm Kept. I'll quietly watch this channel for promises people make, and ask "
                  "before I track anything. Type *kept help* to see what I can do."),
        )
    except Exception:
        log.exception("welcome failed")


# ---- agent panel -----------------------------------------------------------------

assistant = Assistant()


@assistant.thread_started
def on_assistant_start(say, set_suggested_prompts):
    say("Ask me what your team has promised, and I'll pull it live from your channels with source links.")
    try:
        set_suggested_prompts(prompts=[
            {"title": "Promises about the deck", "message": "What did we promise about the deck?"},
        ])
    except Exception:
        log.exception("suggested prompts failed")


@assistant.user_message
def on_assistant_message(payload, say, set_status):
    try:
        set_status("searching your channels")
    except Exception:
        pass
    say(recall.answer(payload.get("text", "")))


app.assistant(assistant)


# ---- helpers ---------------------------------------------------------------------

def _ephemeral(client, channel, user, text, blocks_=None):
    client.chat_postEphemeral(channel=channel, user=user, text=text, blocks=blocks_)


def _sync(client, channel_id):
    try:
        ledger.sync(client, channel_id)
    except Exception:
        # the promise is already stored; the canvas catches up on the next change
        log.exception("ledger sync failed")


def _modal_values(view):
    """Pull (description, due_date, due_time) out of an edit/track modal submission."""
    v = view["state"]["values"]
    desc = v["e_desc"]["val"].get("value")
    due_date = v["e_date"]["val"].get("selected_date")
    due_time = v["e_time"]["val"].get("selected_time")
    return desc, due_date, due_time


def _when(due_date, due_time=None):
    return blocks._when(due_date, due_time)


def _stats_text(channel_id):
    rows = store.get_stats(channel_id, date.today().isoformat())
    if not rows:
        return "No promises tracked here yet, so there is no kept-rate to show."
    lines = ["*Kept-rate for this channel*"]
    for r in rows:
        kept, slipped = r["kept"] or 0, r["slipped"] or 0
        total = kept + slipped
        rate = f"{round(100 * kept / total)}%" if total else "n/a"
        lines.append(f"• *{r['owner_name']}*  {kept} kept, {slipped} slipped  (kept-rate {rate})")
    return "\n".join(lines)


# the boilerplate verbs and articles that most promises share; matching on them is what
# made "send the numbers" false-match "send the design file".
_RESCHEDULE_STOP = {"send", "get", "call", "finish", "do", "make", "give", "share", "the",
                    "a", "an", "to", "you", "your", "i", "we", "will", "ll", "by", "on",
                    "for", "of", "up", "over", "back", "with", "about", "them", "him", "her"}


def _key_terms(desc: str) -> set:
    """The distinctive words of a promise, dropping the shared 'send the ...' boilerplate."""
    return {w for w in re.findall(r"[a-z0-9]+", desc.lower()) if w not in _RESCHEDULE_STOP}


def _reschedule_match(owner_id, channel_id, found):
    """The open promise this owner already has here that this message likely just moves to
    a new date. Matches on the promise's distinctive words (the object, not the verb), so a
    shared prefix does not false-match, and only when the date actually changes."""
    if not found.get("due_date"):
        return None
    want = _key_terms(found["description"])
    if not want:
        return None
    best, best_overlap = None, 0.0
    for p in store.get_open_by_owner(owner_id, channel_id):
        have = _key_terms(p["description"])
        if not have:
            continue
        overlap = len(want & have) / min(len(want), len(have))
        if overlap > best_overlap:
            best, best_overlap = p, overlap
    if best and best_overlap >= config.RESCHEDULE_MATCH and best["due_date"] != found["due_date"]:
        return best
    return None


def _resolve_recipient(client, recipient):
    """Turn a raw <@U123> mention into a readable name; leave a plain name as it is."""
    if not recipient:
        return None
    m = re.fullmatch(r"<@([A-Z0-9]+)>|@?([UW][A-Z0-9]{6,})", recipient.strip())
    if m:
        return _display_name(client, m.group(1) or m.group(2))
    return recipient


def _match_keywords(low):
    if "digest" in low or "weekly update" in low or "client update" in low:
        return "digest"
    if "kept rate" in low or "reliab" in low or low in ("stats", "score", "scorecard"):
        return "stats"
    if "my promise" in low or "what do i owe" in low or "what are my" in low or low in ("promises", "mine"):
        return "mine"
    if low in ("help", "?", "commands") or "what can you" in low:
        return "help"
    return None


def _channel_command(text):
    """A command only counts in a channel if aimed at Kept. An @mention is an explicit
    ping, so an unclear one still gets help. A bare 'kept ...' only counts when it names a
    real command; otherwise it is ordinary chat and falls through to promise detection, so
    'kept the receipts' is not a command and a promise starting with 'kept' is not eaten."""
    t = text.strip()
    if BOT_USER_ID and t.startswith(f"<@{BOT_USER_ID}>"):
        return _match_keywords(t[len(f"<@{BOT_USER_ID}>"):].strip().lower()) or "help"
    low = t.lower()
    if low == "kept":
        return "help"
    if low.startswith("kept "):
        return _match_keywords(low[5:].strip())   # a recognised command, else None (chat)
    return None


def _dm_command(text):
    return _match_keywords(text.lower().strip())


def _is_smalltalk(text):
    low = text.lower().strip().rstrip("!.")
    return len(low) < 4 or low in GREETINGS


def _display_name(client, user_id):
    try:
        p = client.users_info(user=user_id)["user"]
        return p["profile"].get("display_name") or p.get("real_name") or "someone"
    except Exception:
        return "someone"


def _channel_name(client, channel_id):
    try:
        return client.conversations_info(channel=channel_id)["channel"].get("name", "")
    except Exception:
        return ""


def _permalink(client, channel_id, ts):
    try:
        return client.chat_getPermalink(channel=channel_id, message_ts=ts)["permalink"]
    except Exception:
        return None


if __name__ == "__main__":
    store.init_db()
    try:
        BOT_USER_ID = app.client.auth_test()["user_id"]
        log.info("Kept bot user id %s", BOT_USER_ID)
    except Exception:
        log.exception("auth_test failed, member-join welcome and mention commands may be off")
    scheduler.start(app.client)
    log.info("Kept is starting up, Socket Mode.")
    SocketModeHandler(app, config.SLACK_APP_TOKEN).start()
