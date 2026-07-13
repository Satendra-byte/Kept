"""Block Kit builders. Pure functions that return block lists, which Slack renders
into real cards. Buttons carry only the promise id (an opaque integer) or a pending
key, never the promise fields, so a tampered click cannot inject data."""


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


def _when(due_date, due_time=None) -> str:
    """How a deadline reads on a card: a day, a day and time, or nothing set."""
    if not due_date:
        return "no date given"
    return f"{due_date} {due_time}" if due_time else due_date


def confirm_blocks(promise: dict) -> list:
    """The private 'Track it?' card shown to the person who made the promise."""
    pid = str(promise["id"])
    meta = f"owner  *{promise['owner_name']}*"
    if promise.get("recipient"):
        meta += f"      to  *{promise['recipient']}*"
    meta += f"      due  *{_when(promise['due_date'], promise.get('due_time'))}*"
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


def nudge_blocks(promise: dict, overdue: bool = False) -> list:
    """The private DM sent to the owner when a promise is due, or a sharper re-nudge once
    it has blown past the deadline."""
    pid = str(promise["id"])
    when = _when(promise["due_date"], promise.get("due_time"))
    head = (f":warning: This one is overdue (was due *{when}*):\n{promise['description']}"
            if overdue else
            f"Your promise is due *{when}*:\n{promise['description']}")
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": head}},
        {
            "type": "actions",
            "elements": [
                _btn("Mark kept", "mark_kept", pid, primary=True),
                _btn("Need more time", "need_time", pid),
            ],
        },
    ]


def my_promises_blocks(promises: list[dict]) -> list:
    """The 'my promises' list: each open promise with its own Mark kept / Reschedule /
    Edit buttons, so an owner can settle any of them without waiting for a nudge."""
    if not promises:
        return [{"type": "section",
                 "text": {"type": "mrkdwn", "text": "You have no open promises. All clear."}}]
    out = [{"type": "section",
            "text": {"type": "mrkdwn", "text": f"*Your open promises ({len(promises)})*"}}]
    for p in promises:
        pid = str(p["id"])
        to = f"  to *{p['recipient']}*" if p.get("recipient") else ""
        out.append({"type": "section", "text": {"type": "mrkdwn",
                    "text": f"{p['description']}{to}\n_due {_when(p['due_date'], p.get('due_time'))}_"}})
        out.append({"type": "actions", "elements": [
            _btn("Mark kept", "mark_kept", pid, primary=True),
            _btn("Need more time", "need_time", pid),
            _btn("Edit", "edit_tracked", pid),
        ]})
    return out


def _edit_inputs(description=None, due_date=None, due_time=None) -> list:
    """The shared description / date / time inputs used by the edit and track modals."""
    desc = {"type": "plain_text_input", "action_id": "val"}
    if description:
        desc["initial_value"] = description
    date = {"type": "datepicker", "action_id": "val"}
    if due_date:
        date["initial_date"] = due_date
    time = {"type": "timepicker", "action_id": "val"}
    if due_time:
        time["initial_time"] = due_time
    return [
        {"type": "input", "block_id": "e_desc",
         "label": {"type": "plain_text", "text": "Promise"}, "element": desc},
        {"type": "input", "block_id": "e_date", "optional": True,
         "label": {"type": "plain_text", "text": "Due date"}, "element": date},
        {"type": "input", "block_id": "e_time", "optional": True,
         "label": {"type": "plain_text", "text": "Due time (optional)"}, "element": time},
    ]


def edit_modal(promise_id, description, due_date=None, due_time=None) -> dict:
    """Edit an already-tracked promise: wording, date, time. Carries only the id."""
    return {
        "type": "modal", "callback_id": "edit_submit", "private_metadata": str(promise_id),
        "title": {"type": "plain_text", "text": "Edit promise"},
        "submit": {"type": "plain_text", "text": "Save"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": _edit_inputs(description, due_date, due_time),
    }


def track_modal(key, description, due_date=None, due_time=None) -> dict:
    """Confirm-and-adjust before tracking (the message action, and the Edit button on the
    confirm card): tweak the date or wording, then Track. Carries only the pending key."""
    return {
        "type": "modal", "callback_id": "track_submit", "private_metadata": str(key),
        "title": {"type": "plain_text", "text": "Track promise"},
        "submit": {"type": "plain_text", "text": "Track it"},
        "close": {"type": "plain_text", "text": "Cancel"},
        "blocks": _edit_inputs(description, due_date, due_time),
    }


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


def digest_blocks(key, text) -> list:
    """A drafted weekly client update, reviewed by a human before it posts to the channel."""
    return [
        {"type": "section", "text": {"type": "mrkdwn", "text": f"*Weekly update draft:*\n\n{text}"}},
        {"type": "actions", "elements": [
            _btn("Post to channel", "post_digest", str(key), primary=True),
            _btn("Not now", "dismiss_draft", str(key)),
        ]},
    ]


def reschedule_match_blocks(key, existing_desc, new_when) -> list:
    """Shown when a new message looks like it moves an existing promise's date rather than
    making a new one. The human decides: update the old one, or track this as new."""
    return [
        {"type": "section", "text": {"type": "mrkdwn",
         "text": f"*Looks like an update to an earlier promise:*\n{existing_desc}"}},
        {"type": "context", "elements": [{"type": "mrkdwn", "text": f"new timing  *{new_when}*"}]},
        {"type": "actions", "elements": [
            _btn("Reschedule it", "reschedule_match", str(key), primary=True),
            _btn("Track as new", "track_new", str(key)),
            _btn("Ignore", "ignore_promise", str(key)),
        ]},
    ]


if __name__ == "__main__":
    # Pure, no secrets needed. Runs standalone: python -m backend.blocks
    p = {"id": 7, "description": "revised deck", "owner_name": "Sachin",
         "recipient": "Priya", "due_date": "2026-07-10", "due_time": "17:00"}

    built = confirm_blocks(p)
    ctx = [b for b in built if b["type"] == "context"][0]["elements"][0]["text"]
    assert "to  *Priya*" in ctx  # recipient shows on the card when present
    assert "2026-07-10 17:00" in ctx  # date and time both show

    actions = [b for b in built if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in actions] == ["track_promise", "edit_promise", "ignore_promise"]
    assert all(a["value"] == "7" for a in actions)  # buttons carry only the id, nothing else

    nudge = [b for b in nudge_blocks(p) if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in nudge] == ["mark_kept", "need_time"]
    assert all(a["value"] == "7" for a in nudge)
    over = nudge_blocks(p, overdue=True)[0]["text"]["text"]
    assert "overdue" in over.lower()  # escalation wording differs

    mine = my_promises_blocks([p])
    macts = [b for b in mine if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in macts] == ["mark_kept", "need_time", "edit_tracked"]
    assert my_promises_blocks([])[0]["text"]["text"].endswith("All clear.")  # empty case

    em = edit_modal(7, "revised deck", "2026-07-10", "17:00")
    assert em["callback_id"] == "edit_submit" and em["private_metadata"] == "7"
    assert em["blocks"][1]["element"]["initial_date"] == "2026-07-10"
    assert em["blocks"][2]["element"]["initial_time"] == "17:00"

    tm = track_modal("ts9", "send deck", "2026-07-10")
    assert tm["callback_id"] == "track_submit" and tm["private_metadata"] == "ts9"
    assert "initial_time" not in tm["blocks"][2]["element"]  # no time given, none prefilled

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

    dig = digest_blocks("digest:C1", "Done: the deck. In progress: the report.")
    digact = [b for b in dig if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in digact] == ["post_digest", "dismiss_draft"]
    assert digact[0]["value"] == "digest:C1"

    rm = reschedule_match_blocks("ts5", "send the deck", "2026-07-14")
    rmact = [b for b in rm if b["type"] == "actions"][0]["elements"]
    assert [a["action_id"] for a in rmact] == ["reschedule_match", "track_new", "ignore_promise"]
    assert all(a["value"] == "ts5" for a in rmact)

    print("blocks self-check passed")
