"""The Promise Ledger, a canvas pinned to the channel that mirrors the stored
promises. Regenerated in full on every change: one 'replace' edit with no section
id, so there is no section bookkeeping to drift. Slack allows one canvas per
channel, so we create it once and edit it from then on."""
from datetime import date

from backend import store


def _cell(text: str) -> str:
    # a stray pipe or newline in a promise would break the markdown table
    return text.replace("|", "\\|").replace("\n", " ").strip()


def _rows(promises: list, date_label: str, date_key: str) -> list:
    """Table rows for a bucket of promises. date_key is 'due_date' or 'kept_at'."""
    out = [f"| Promise | Owner | To | {date_label} |", "| --- | --- | --- | --- |"]
    for p in promises:
        desc = _cell(p["description"])
        if p.get("source_permalink"):
            desc = f"[{desc}]({p['source_permalink']})"
        to = _cell(p.get("recipient") or "-")
        if date_key == "kept_at":
            when = (p["kept_at"] or "")[:10]
        else:
            when = p["due_date"] or "no date"
            if p.get("due_time"):
                when = f"{when} {p['due_time']}"       # a timed deadline shows the clock time
        out.append(f"| {desc} | {_cell(p['owner_name'])} | {to} | {when} |")
    return out


def render(promises: list[dict], today: str | None = None) -> str:
    """The full ledger markdown. Pure, so the self-check below runs standalone. Open
    promises past their due date get their own Overdue section at the top."""
    today = today or date.today().isoformat()
    overdue = [p for p in promises
               if p["status"] == "open" and p["due_date"] and p["due_date"] < today]
    upcoming = [p for p in promises
                if p["status"] == "open" and not (p["due_date"] and p["due_date"] < today)]
    kept = [p for p in promises if p["status"] == "kept"]

    out = ["# Promise Ledger", "",
           "_Kept keeps this current. Every commitment your team makes, to a teammate or a client, lives here._", ""]

    if overdue:
        out += [f"## Overdue ({len(overdue)})", ""] + _rows(overdue, "Due", "due_date") + [""]

    out += [f"## Open ({len(upcoming)})", ""]
    out += (_rows(upcoming, "Due", "due_date") if upcoming else ["Nothing open. All caught up."]) + [""]

    if kept:
        out += [f"## Kept ({len(kept)})", ""] + _rows(kept, "Kept", "kept_at")

    return "\n".join(out)


def sync(client, channel_id: str) -> None:
    """Rebuild the channel's ledger canvas from the store. Caller must have a channels
    row already (upsert_channel), so set_canvas has a row to write the id to."""
    content = {"type": "markdown", "markdown": render(store.get_by_channel(channel_id))}
    canvas_id = store.get_canvas(channel_id)
    if canvas_id:
        client.canvases_edit(canvas_id=canvas_id, changes=[{"operation": "replace", "document_content": content}])
    else:
        # ponytail: if the canvas exists in Slack but our id is lost, this 500s with
        # "already exists". Fresh channels never hit it; add a conversations.info
        # lookup to recover the id if it ever bites in testing.
        resp = client.conversations_canvases_create(channel_id=channel_id, document_content=content)
        store.set_canvas(channel_id, resp["canvas_id"])


if __name__ == "__main__":
    # Pure render check, no Slack or db needed: python -m backend.ledger
    rows = [
        {"status": "open", "description": "send the revised deck", "owner_name": "Priya",
         "recipient": "Raj", "due_date": "2026-07-10", "due_time": "17:00",
         "source_permalink": "http://x", "kept_at": None},
        {"status": "open", "description": "reply with the a | b split", "owner_name": "Sam",
         "recipient": None, "due_date": None, "source_permalink": None, "kept_at": None},
        {"status": "kept", "description": "send the invoice", "owner_name": "Sachin",
         "recipient": "Priya", "due_date": "2026-07-01", "source_permalink": None, "kept_at": "2026-07-05T09:00:00+00:00"},
    ]
    md = render(rows, today="2026-07-15")               # the deck's 2026-07-10 is now overdue
    assert "## Overdue (1)" in md and "## Open (1)" in md and "## Kept (1)" in md
    assert "[send the revised deck](http://x)" in md   # overdue row, still linked to source
    assert "2026-07-10 17:00" in md                     # a timed deadline shows the clock time
    assert "Raj" in md and "| - |" in md                 # a named recipient, and "-" when none
    assert "a \\| b" in md                              # pipe escaped so the table survives
    assert "2026-07-05" in md and "T09" not in md       # kept timestamp trimmed to the day

    empty = render([])
    assert "Nothing open. All caught up." in empty
    assert "## Overdue" not in empty and "## Kept" not in empty  # no empty sections

    print("ledger self-check passed")
