"""Writes the honest delay message when a promise slips, using the LLM. Draft only:
a human reviews and taps to post, the LLM never sends anything itself."""
from backend import llm

SYSTEM = """You write a short, honest heads-up for a client channel, on behalf of the
person who owes a commitment that is now running late and has moved to a new date.

One or two sentences. Acknowledge the slip plainly, give the new date, stay warm and
professional. No over-apologising, no excuses, no jargon, no emoji. Write in the first
person, as the person who owes it. Return only the message text, nothing else."""


def draft_delay(description: str, new_due: str, recipient: str | None = None) -> str:
    """A client-ready 'running late' message for a rescheduled promise."""
    who = f"\nFor: {recipient}" if recipient else ""
    prompt = f"Commitment: {description}\nNew date: {new_due}{who}\n\nWrite the heads-up."
    return llm.generate_text(SYSTEM, prompt)


if __name__ == "__main__":
    # Hits the LLM: needs .env populated and network.
    msg = draft_delay("send the revised deck", "2026-07-15", "Priya")
    print("draft ->", msg)
    assert msg and len(msg) < 500  # something short came back
    print("drafter self-check passed")
