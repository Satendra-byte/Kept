"""The single seam to the LLM. Every AI call goes through here, so swapping
provider is a one-file change."""
import json

from google import genai
from google.genai import types

from backend import config

_client = genai.Client(api_key=config.GEMINI_API_KEY)


def generate_json(system: str, prompt: str) -> dict:
    """Classify or extract. Returns a JSON object. Used by the extractor."""
    resp = _client.models.generate_content(
        model=config.LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            temperature=0,  # deterministic: same message, same read
        ),
    )
    return json.loads(resp.text)


def generate_text(system: str, prompt: str) -> str:
    """Write prose. Returns text. Used by the drafter."""
    resp = _client.models.generate_content(
        model=config.LLM_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.4,  # a little warmth in the wording
        ),
    )
    return resp.text.strip()
