"""The Kept app. Hears messages, runs the extractor, drives the confirm flow.
Socket Mode, so no public URL is needed. Run: python -m backend.app"""
import logging
from datetime import date

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from backend import blocks, config, drafter, extractor, ledger, scheduler, store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kept")

app = App(token=config.SLACK_BOT_TOKEN)

# Promises awaiting a Track tap, keyed by the source message ts. The button carries
# this key, never the promise text, so a tampered click cannot inject a promise.
# In memory on purpose: lost on restart, which is fine for confirmations in flight.
pending: dict[str, dict] = {}

# Drafted delay messages awaiting a Post tap, keyed by promise id. Button carries only
# the id; in memory on purpose, a draft in flight is fine to lose on restart.
pending_drafts: dict[str, dict] = {}


@app.event("message")
def on_message(event, client):
    # only plain messages in channels, never bots, our own, DMs, edits or joins
    if event.get("bot_id") or event.get("subtype"):
        return
    if event.get("channel_type") not in ("channel", "group"):
        return
    text = event.get("text", "")
    if len(text) < config.MIN_MESSAGE_CHARS:
        return

    user_id = event["user"]
    author = _display_name(client, user_id)
    found = extractor.extract(text, author, date.today().isoformat())
    if not found:
        return

    key = event["ts"]
    pending[key] = {
        "channel_id": event["channel"],
        "owner_id": user_id,
        "owner_name": author,
        "description": found["description"],
        "recipient": found.get("recipient"),
        "due_date": found["due_date"],
        "source_ts": event["ts"],
    }
    client.chat_postEphemeral(
        channel=event["channel"],
        user=user_id,
        blocks=blocks.confirm_blocks(
            {"id": key, "description": found["description"], "owner_name": author,
             "recipient": found.get("recipient"), "due_date": found["due_date"]}
        ),
        text="Track this commitment?",
    )


@app.action("track_promise")
def on_track(ack, body, client, respond):
    ack()
    data = pending.pop(body["actions"][0]["value"], None)
    if not data:
        respond(replace_original=True, text="That confirmation expired. Say it again if you still want it tracked.")
        return

    store.upsert_channel(data["channel_id"], _channel_name(client, data["channel_id"]))
    store.add_promise(
        data["channel_id"], data["owner_id"], data["owner_name"],
        data["description"], data["due_date"], _permalink(client, data["channel_id"], data["source_ts"]),
        recipient=data.get("recipient"),
    )
    try:
        ledger.sync(client, data["channel_id"])
    except Exception:
        # the promise is already stored; the canvas catches up on the next track
        log.exception("ledger sync failed")
    due = data["due_date"] or "no date"
    respond(replace_original=True, text=f'Tracked. "{data["description"]}" is in the ledger, due {due}.')


@app.action("ignore_promise")
def on_ignore(ack, body, respond):
    ack()
    pending.pop(body["actions"][0]["value"], None)
    respond(replace_original=True, text="Okay, leaving that one alone.")


@app.action("edit_promise")
def on_edit(ack, respond):
    ack()
    respond(replace_original=True, text="Editing is coming soon. For now reword it and say it again, or track it as is.")


@app.shortcut("track_message")
def on_track_message(ack, shortcut, client):
    """Track any message the user picks: their own, a teammate's, a client's. This is
    how a promise that formed across a conversation, or one someone else made, gets in.
    The human choosing the message is the confirmation, so there is no second card."""
    ack()
    channel_id = shortcut["channel"]["id"]
    invoker = shortcut["user"]["id"]
    msg = shortcut["message"]
    author_id = msg.get("user") or invoker  # owner is who made it, else who tracked it
    author = _display_name(client, author_id)

    found = extractor.extract(msg.get("text", ""), author, date.today().isoformat())
    if not found:
        client.chat_postEphemeral(
            channel=channel_id, user=invoker,
            text="I couldn't find a promise in that message, so I left it alone.",
        )
        return

    store.upsert_channel(channel_id, _channel_name(client, channel_id))
    store.add_promise(
        channel_id, author_id, author, found["description"], found["due_date"],
        _permalink(client, channel_id, msg["ts"]), recipient=found.get("recipient"),
    )
    try:
        ledger.sync(client, channel_id)
    except Exception:
        log.exception("ledger sync failed")
    due = found["due_date"] or "no date"
    client.chat_postEphemeral(
        channel=channel_id, user=invoker,
        text=f'Tracked. "{found["description"]}" is in the ledger, due {due}.',
    )


@app.action("mark_kept")
def on_mark_kept(ack, body, client, respond):
    ack()
    pid = int(body["actions"][0]["value"])
    store.mark_kept(pid)
    p = store.get(pid)
    if p:
        try:
            ledger.sync(client, p["channel_id"])
        except Exception:
            log.exception("ledger sync failed")
    respond(replace_original=True, text="Marked as kept. Nice work.")


@app.action("need_time")
def on_need_time(ack, body, client):
    ack()
    client.views_open(
        trigger_id=body["trigger_id"],
        view=blocks.reschedule_modal(body["actions"][0]["value"]),
    )


@app.view("reschedule_submit")
def on_reschedule(ack, view, client):
    ack()
    pid = int(view["private_metadata"])
    new_due = view["state"]["values"]["new_due"]["date"]["selected_date"]
    store.reschedule(pid, new_due)
    p = store.get(pid)
    if not p:
        return
    try:
        ledger.sync(client, p["channel_id"])
    except Exception:
        log.exception("ledger sync failed")
    # offer the owner a drafted client heads-up about the slip
    try:
        text = drafter.draft_delay(p["description"], new_due, p.get("recipient"))
        pending_drafts[str(pid)] = {"text": text, "channel_id": p["channel_id"]}
        dm = client.conversations_open(users=p["owner_id"])["channel"]["id"]
        client.chat_postMessage(channel=dm, blocks=blocks.draft_blocks(str(pid), text),
                                text="A heads-up you can send the client")
    except Exception:
        log.exception("draft delay failed")


@app.action("post_draft")
def on_post_draft(ack, body, client, respond):
    ack()
    d = pending_drafts.pop(body["actions"][0]["value"], None)
    if not d:
        respond(replace_original=True, text="That draft expired. Reschedule again for a fresh one.")
        return
    client.chat_postMessage(channel=d["channel_id"], text=d["text"])
    respond(replace_original=True, text="Posted to the channel.")


@app.action("dismiss_draft")
def on_dismiss_draft(ack, body, respond):
    ack()
    pending_drafts.pop(body["actions"][0]["value"], None)
    respond(replace_original=True, text="Okay, not sending it.")


def _display_name(client, user_id: str) -> str:
    try:
        p = client.users_info(user=user_id)["user"]
        return p["profile"].get("display_name") or p.get("real_name") or "someone"
    except Exception:
        return "someone"


def _channel_name(client, channel_id: str) -> str:
    try:
        return client.conversations_info(channel=channel_id)["channel"].get("name", "")
    except Exception:
        return ""


def _permalink(client, channel_id: str, ts: str):
    try:
        return client.chat_getPermalink(channel=channel_id, message_ts=ts)["permalink"]
    except Exception:
        return None


if __name__ == "__main__":
    store.init_db()
    scheduler.start(app.client)
    log.info("Kept is starting up, Socket Mode.")
    SocketModeHandler(app, config.SLACK_APP_TOKEN).start()
