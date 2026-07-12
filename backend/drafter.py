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


if __name__ == "__main__":
    # Hits the LLM for the body; the greeting is deterministic.
    got = draft_delay("send the code", "2026-07-13", "satendraT")
    print("to satendraT ->", got)
    assert got.startswith("Hi satendraT, ")  # exact name, built in code not by the LLM

    print("no name ->", draft_delay("send the deck", "2026-07-15"))
    print("drafter self-check passed")
