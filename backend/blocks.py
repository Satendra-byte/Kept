"""Block Kit builders. Pure functions that return block lists, which Slack renders
into real cards. Buttons carry only the promise id (an opaque integer), never the
promise fields, so a tampered click cannot inject data."""


def _btn(text: str, action_id: str, value: str, primary: bool = False) -> dict:
    b = {
        "type": "button",
        "text": {"type": "plain_text", "text": text},
        "action_id": action_id,
        "value": value,
    }
    if primary:
        b["style"] = "primary"
    return b


def confirm_blocks(promise: dict) -> list:
    """The private 'Track it?' card shown to the person who made the promise."""
    due = promise["due_date"] or "no date given"
    pid = str(promise["id"])
    meta = f"owner  *{promise['owner_name']}*"
    if promise.get("recipient"):
        meta += f"      to  *{promise['recipient']}*"
    meta += f"      due  *{due}*"
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*Track this commitment?*\n{promise['description']}"},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": meta}],
        },
        {
            "type": "actions",
            "elements": [
                _btn("Track it", "track_promise", pid, primary=True),
                _btn("Edit", "edit_promise", pid),
                _btn("Ignore", "ignore_promise", pid),
            ],
        },
    ]


def nudge_blocks(promise: dict) -> list:
    """The private DM sent to the owner before a promise is due."""
    pid = str(promise["id"])
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"Your promise is due *{promise['due_date']}*:\n{promise['description']}"},
        },
        {
            "type": "actions",
            "elements": [
                _btn("Mark kept", "mark_kept", pid, primary=True),
                _btn("Need more time", "need_time", pid),
            ],
        },
    ]


def reschedule_modal(promise_id) -> dict:
    """The 'Need more time' modal: pick a new due date. Carries only the promise id."""
    return {
        "type": "modal",
        "callback_id": "reschedule_submit",
        "private_metadata": str(promise_id),
        "title": {"type": "plain_text", "text": "Need more time"},
        "submit": {"type": "plain_text", "text": "Reschedule"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": [
            {
                "type": "input",
                "block_id": "new_due",
                "label": {"type": "plain_text", "text": "New due date"},
                "element": {"type": "datepicker", "action_id": "date"},
            }
        ],
    }


def draft_blocks(promise_id, text, recipient=None) -> list:
    """The drafted heads-up shown to the owner. A promise to one person is theirs to
    send privately (no auto-post); a promise to the channel gets a one-tap Post."""
    pid = str(promise_id)
    if recipient:
        header = f"*Draft for {recipient}, send it to them directly:*"
        actions = [_btn("Not now", "dismiss_draft", pid)]
    else:
        header = "*Draft for the client, your call to send:*"
        actions = [
            _btn("Post to channel", "post_draft", pid, primary=True),
            _btn("Not now", "dismiss_draft", pid),
        ]
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"{header}\n\n{text}"}},
        {"type": "actions", "elements": actions},
    ]


if __name__ == "__main__":
    # Pure, no secrets needed. Runs standalone: python -m backend.blocks
    p = {"id": 7, "description": "revised deck", "owner_name": "Sachin",
         "recipient": "Priya", "due_date": "2026-07-10"}

    built = confirm_blocks(p)
    ctx = [b for b in built if b["type"] == "context"][0]["elements"][0]["text"]
    assert "to  *Priya*" in ctx  # recipient shows on the card when present

    actions = [b for b in built if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in actions] == ["track_promise", "edit_promise", "ignore_promise"]
    assert all(a["value"] == "7" for a in actions)  # buttons carry only the id, nothing else

    nudge = [b for b in nudge_blocks(p) if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in nudge] == ["mark_kept", "need_time"]
    assert all(a["value"] == "7" for a in nudge)

    modal = reschedule_modal(7)
    assert modal["callback_id"] == "reschedule_submit" and modal["private_metadata"] == "7"
    assert modal["blocks"][0]["element"]["type"] == "datepicker"

    draft = draft_blocks(7, "Running a bit behind on the deck, you will have it Friday.")
    dact = [b for b in draft if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in dact] == ["post_draft", "dismiss_draft"]  # channel: one-tap post
    assert all(a["value"] == "7" for a in dact)

    priv = draft_blocks(7, "Hi John, running behind, you will have it Friday.", recipient="John")
    pact = [b for b in priv if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in pact] == ["dismiss_draft"]  # person: owner sends it privately

    print("blocks self-check passed")
