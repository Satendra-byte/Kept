"""The single seam to the LLM. Every AI call goes through here, so swapping provider is
a one-file change. Transient upstream errors (503 overloaded, 429 rate limit) are retried
with a short backoff, so one blip does not silently drop a detection mid-demo."""
import json
import time

from google import genai
from google.genai import types

from backend import config

_client = genai.Client(api_key=config.GEMINI_API_KEY)

# HTTP codes worth retrying: rate limit and the 5xx transient family. Everything else
# (bad key, bad request) will not fix itself, so it is raised straight away.
_RETRYABLE = {429, 500, 502, 503, 504}


def _generate(system: str, prompt: str, **cfg):
    """One content call, retried up to three times on a transient upstream error."""
    conf = types.GenerateContentConfig(system_instruction=system, **cfg)
    for attempt in range(3):
        try:
            return _client.models.generate_content(model=config.LLM_MODEL, contents=prompt, config=conf)
        except Exception as e:
            if attempt == 2 or getattr(e, "code", None) not in _RETRYABLE:
                raise
            time.sleep(1.5 * (attempt + 1))   # 1.5s then 3s; a 503 usually clears fast


def generate_json(system: str, prompt: str) -> dict:
    """Classify or extract. Returns a JSON object. Used by the extractor."""
    return json.loads(_generate(system, prompt, response_mime_type="application/json", temperature=0).text)


def generate_text(system: str, prompt: str) -> str:
    """Write prose. Returns text. Used by the drafter."""
    return _generate(system, prompt, temperature=0.4).text.strip()
