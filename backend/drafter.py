"""Writes the honest delay message when a promise slips, using the LLM. Draft only:
a human reviews and taps to post, the LLM never sends anything itself."""
from backend import llm

SYSTEM = """You write a short, honest heads-up about a commitment that is now running
late and has moved to a new date, on behalf of the person who owes it.

One or two sentences, first person. Open by addressing the recipient by their first
name if one is given (for example "Hi Priya,"), otherwise open with "Hi team,".
Acknowledge the slip plainly, give the new date, stay warm and professional. No
over-apologising, no excuses, no jargon, no emoji. Return only the message text."""


def draft_delay(description: str, new_due: str, recipient: str | None = None) -> str:
    """A client-ready 'running late' message for a rescheduled promise."""
    who = f"\nFor: {recipient}" if recipient else ""
    prompt = f"Commitment: {description}\nNew date: {new_due}{who}\n\nWrite the heads-up."
    return llm.generate_text(SYSTEM, prompt)


if __name__ == "__main__":
    # Hits the LLM: needs .env populated and network.
    got = draft_delay("send the code", "2026-07-13", "John")
    print("to John ->", got)
    assert "John" in got  # addresses the named recipient

    print("no name ->", draft_delay("send the deck", "2026-07-15"))

    assert got and len(got) < 500
    print("drafter self-check passed")
