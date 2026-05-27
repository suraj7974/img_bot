"""Gemini AI wrapper.

A single class that owns the Gemini client and exposes the two pipeline calls:

    client = GeminiClient()
    prompts = client.generate_prompts("my topic and facts")  # -> list[str]
    image_bytes = client.generate_image(prompts[0])
"""

import os

from dotenv import load_dotenv
from google import genai

import config
import prompts

_NUMBER_WORDS = {1: "ONE", 2: "TWO", 3: "THREE", 4: "FOUR", 5: "FIVE", 6: "SIX"}


def _count_word(n: int) -> str:
    """Spell a small count for the prompt (falls back to the digit)."""
    return _NUMBER_WORDS.get(n, str(n))


class GeminiClient:
    """Thin, typed wrapper around the Gemini SDK for this pipeline."""

    def __init__(self, api_key: str | None = None):
        load_dotenv()
        key = api_key or os.getenv("GEMINI_API_KEY")
        if not key:
            raise RuntimeError(
                "GEMINI_API_KEY is not set. Add it to your environment or a .env file."
            )
        self._client = genai.Client(api_key=key)

    # -- Step 1: query -> N detailed image prompts (same data, diff design) -- #
    def generate_prompts(self, user_query: str) -> list[str]:
        """Expand a short user query into NUM_VARIANTS image-generation prompts.

        The text model returns the variants separated by a `===VARIANT===` line;
        we split on that delimiter. All variants carry the same data and differ
        only in design.
        """
        n = config.NUM_VARIANTS
        instruction = (
            prompts.SYSTEM_PROMPT
            .replace("{COUNT}", _count_word(n))
            .replace("{User Query}", user_query.strip())
        )
        response = self._client.models.generate_content(
            model=config.TEXT_MODEL,
            contents=instruction,
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Text model returned an empty response.")

        variants = [p.strip() for p in text.split("===VARIANT===") if p.strip()]
        if not variants:
            raise RuntimeError("Text model returned no usable prompts.")
        return variants[:n]  # never produce more than configured, even if the model over-returns

    # -- Step 2: detailed prompt -> image bytes ----------------------------- #
    def generate_image(self, prompt: str) -> bytes:
        """Return the raw bytes of the first image generated for the prompt."""
        response = self._client.models.generate_content(
            model=config.IMAGE_MODEL,
            contents=prompt,
        )
        for candidate in getattr(response, "candidates", None) or []:
            content = getattr(candidate, "content", None)
            for part in getattr(content, "parts", None) or []:
                inline = getattr(part, "inline_data", None)
                if inline is not None and inline.data:
                    return inline.data

        text = getattr(response, "text", None)
        raise RuntimeError(
            "Image model returned no image."
            + (f" Model said: {text}" if text else "")
        )
