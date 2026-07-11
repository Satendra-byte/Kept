"""The Kept app. Hears messages, runs the extractor, drives the confirm flow.
Socket Mode, so no public URL is needed. Run: python -m backend.app"""
import logging
from datetime import date

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from backend import blocks, config, extractor, ledger, store

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("kept")

app = App(token=config.SLACK_BOT_TOKEN)

# Promises awaiting a Track tap, keyed by the source message ts. The button carries
# this key, never the promise text, so a tampered click cannot inject a promise.
# In memory on purpose: lost on restart, which is fine for confirmations in flight.
pending: dict[str, dict] = {}


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
        "due_date": found["due_date"],
        "source_ts": event["ts"],
    }
    client.chat_postEphemeral(
        channel=event["channel"],
        user=user_id,
        blocks=blocks.confirm_blocks(
            {"id": key, "description": found["description"], "owner_name": author, "due_date": found["due_date"]}
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
    log.info("Kept is starting up, Socket Mode.")
    SocketModeHandler(app, config.SLACK_APP_TOKEN).start()
