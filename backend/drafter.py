"""Writes the honest delay message when a promise slips, using the LLM. Draft only:
a human reviews and taps to post, the LLM never sends anything itself."""
from backend import llm

SYSTEM = """You write the body of a short, honest heads-up that a commitment is running
late and has moved to a new date, on behalf of the person who owes it.

One or two sentences, first person. Do NOT write a greeting or any name, start straight
with the apology (for example "I'm a bit behind on the deck..."). Acknowledge the slip
plainly, give the new date, stay warm and professional. No excuses, no jargon, no
emoji, no sign-off. Return only the sentences."""


def draft_delay(description: str, new_due: str, recipient: str | None = None) -> str:
    """A client-ready 'running late' message for a rescheduled promise. The greeting is
    built in code so the recipient's exact name is used; the LLM writes only the body."""
    prompt = f"Commitment: {description}\nNew date: {new_due}\n\nWrite the apology sentences."
    body = llm.generate_text(SYSTEM, prompt)
    greeting = f"Hi {recipient}," if recipient else "Hi team,"
    return f"{greeting} {body}"


DIGEST_SYSTEM = """You write a short, friendly weekly status update to a client, from a
list of a team's tracked commitments. Group it into what is Done and what is In progress,
one line each, plainest language. Warm and concise, no jargon, no emoji, no sign-off.
Start straight with the update, no greeting. Return only the update text."""


def draft_digest(kept: list[dict], open_: list[dict]) -> str:
    """A weekly client update drafted from the ledger: what shipped, what is still moving.
    Greeting built in code, same as the delay draft; the LLM writes only the body."""
    def _line(p):
        when = p.get("due_date") or "no date"
        return f"- {p['description']} (due {when})" if p.get("status") == "open" \
            else f"- {p['description']}"
    done = "\n".join(_line(p) for p in kept) or "- (nothing yet)"
    doing = "\n".join(_line(p) for p in open_) or "- (nothing open)"
    prompt = f"Done recently:\n{done}\n\nIn progress:\n{doing}\n\nWrite the weekly update."
    return f"Hi team,\n\n{llm.generate_text(DIGEST_SYSTEM, prompt)}"


if __name__ == "__main__":
    # Hits the LLM for the body; the greeting is deterministic.
    got = draft_delay("send the code", "2026-07-13", "satendraT")
    print("to satendraT ->", got)
    assert got.startswith("Hi satendraT, ")  # exact name, built in code not by the LLM

    print("no name ->", draft_delay("send the deck", "2026-07-15"))

    kept = [{"status": "kept", "description": "sent the invoice"}]
    open_ = [{"status": "open", "description": "finish the homepage", "due_date": "2026-07-18"}]
    digest = draft_digest(kept, open_)
    print("digest ->", digest)
    assert digest.startswith("Hi team,")   # greeting built in code, body from the LLM

    print("drafter self-check passed")
