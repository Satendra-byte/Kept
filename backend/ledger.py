"""The Promise Ledger, a canvas pinned to the channel that mirrors the stored
promises. Regenerated in full on every change: one 'replace' edit with no section
id, so there is no section bookkeeping to drift. Slack allows one canvas per
channel, so we create it once and edit it from then on."""
from backend import store


def _cell(text: str) -> str:
    # a stray pipe or newline in a promise would break the markdown table
    return text.replace("|", "\\|").replace("\n", " ").strip()


def render(promises: list[dict]) -> str:
    """The full ledger markdown. Pure, so the self-check below runs standalone."""
    open_ = [p for p in promises if p["status"] == "open"]
    kept = [p for p in promises if p["status"] == "kept"]

    out = [
        "# Promise Ledger",
        "",
        "_Kept keeps this current. Every commitment your team makes to the client lives here._",
        "",
        f"## Open ({len(open_)})",
        "",
    ]
    if open_:
        out += ["| Promise | Owner | To | Due |", "| --- | --- | --- | --- |"]
        for p in open_:
            desc = _cell(p["description"])
            if p.get("source_permalink"):
                desc = f"[{desc}]({p['source_permalink']})"
            to = _cell(p.get("recipient") or "-")
            out.append(f"| {desc} | {_cell(p['owner_name'])} | {to} | {p['due_date'] or 'no date'} |")
    else:
        out.append("Nothing open. All caught up.")
    out.append("")

    if kept:
        out += [f"## Kept ({len(kept)})", "", "| Promise | Owner | To | Kept |", "| --- | --- | --- | --- |"]
        for p in kept:
            to = _cell(p.get("recipient") or "-")
            out.append(f"| {_cell(p['description'])} | {_cell(p['owner_name'])} | {to} | {(p['kept_at'] or '')[:10]} |")

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
         "recipient": "Raj", "due_date": "2026-07-10", "source_permalink": "http://x", "kept_at": None},
        {"status": "open", "description": "reply with the a | b split", "owner_name": "Sam",
         "recipient": None, "due_date": None, "source_permalink": None, "kept_at": None},
        {"status": "kept", "description": "send the invoice", "owner_name": "Sachin",
         "recipient": "Priya", "due_date": "2026-07-01", "source_permalink": None, "kept_at": "2026-07-05T09:00:00+00:00"},
    ]
    md = render(rows)
    assert "## Open (2)" in md
    assert "## Kept (1)" in md
    assert "| Promise | Owner | To | Due |" in md        # recipient column present
    assert "Raj" in md and "| - |" in md                 # a named recipient, and "-" when none
    assert "[send the revised deck](http://x)" in md   # source link kept
    assert "a \\| b" in md                              # pipe escaped so the table survives
    assert "2026-07-05" in md and "T09" not in md       # kept timestamp trimmed to the day

    empty = render([])
    assert "Nothing open. All caught up." in empty
    assert "## Kept" not in empty                        # no kept section when there are none

    print("ledger self-check passed")
