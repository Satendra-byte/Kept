"""Answers 'what did we promise?' from live Slack search (Real-Time Search API), then
has the LLM synthesise a short cited answer. No stored index: the search is live each
time, so nothing from Slack is copied into Kept's own storage."""
import re

from slack_sdk import WebClient

from backend import config, llm

# RTS runs on the user token (search scopes live there), not the bot token.
_search = WebClient(token=config.SLACK_USER_TOKEN)

SYSTEM = """You answer a question about what a team promised, using ONLY the Slack
messages given. Be concise. Name who promised what and by when where the messages say
so, and cite each with its bracket number like [2]. If the messages do not answer the
question, say so plainly. Never invent a promise that is not in the messages."""

MAX_HITS = 8

# Question filler and words like "promise" that people ask with but that never appear
# in the actual messages. Dropping them leaves the topic terms RTS can match on.
_STOP = {"what", "whats", "did", "do", "does", "we", "i", "you", "your", "they", "our",
         "us", "the", "a", "an", "about", "on", "in", "to", "for", "of", "is", "are",
         "was", "were", "have", "has", "had", "when", "who", "any", "anything", "there",
         "that", "this", "promise", "promised", "promises", "commit", "committed"}


def _terms(question: str) -> str:
    """The content words of the question, so RTS matches the topic not the filler."""
    words = [w for w in re.findall(r"[a-z0-9]+", question.lower()) if w not in _STOP]
    return " ".join(words) or question.replace("?", " ").strip()


def answer(question: str) -> str:
    """Search Slack for the question's topic terms, then synthesise a cited answer."""
    resp = _search.api_call("assistant.search.context", params={"query": _terms(question)})
    hits = resp.data.get("results", {}).get("messages", [])[:MAX_HITS]
    if not hits:
        return "I could not find anything relevant in the channels I can see."

    context = "\n".join(f"[{i + 1}] {m.get('author_name', 'someone')}: {m.get('content', '')}"
                        for i, m in enumerate(hits))
    body = llm.generate_text(SYSTEM, f"Question: {question}\n\nMessages:\n{context}\n\nAnswer, citing [n].")

    # show only the sources the answer actually cited, not the whole search context
    cited = {int(n) for n in re.findall(r"\[(\d+)\]", body)}
    sources = "\n".join(f"[{i + 1}] {m.get('permalink', '')}"
                        for i, m in enumerate(hits) if (i + 1) in cited)
    return f"{body}\n\n*Sources*\n{sources}" if sources else body


if __name__ == "__main__":
    # Hits RTS (user token) and the LLM: needs .env and network.
    assert _terms("what did we promise about the file?") == "file"  # filler stripped
    for q in ("what did we promise about the deck?", "what did we promise about the file?"):
        print("Q:", q, "\n", answer(q), "\n---")
