"""Gemini AI wrapper.

A single class that owns the Gemini client and exposes the two pipeline calls:

    client = GeminiClient()
    prompt = client.generate_prompt("my topic and facts")
    image_bytes = client.generate_image(prompt)
"""

import os

from dotenv import load_dotenv
from google import genai

import config
import prompts


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

    # -- Step 1: query -> detailed image prompt ----------------------------- #
    def generate_prompt(self, user_query: str) -> str:
        """Expand a short user query into a dense image-generation prompt."""
        instruction = prompts.SYSTEM_PROMPT.replace("{User Query}", user_query.strip())
        response = self._client.models.generate_content(
            model=config.TEXT_MODEL,
            contents=instruction,
        )
        text = (response.text or "").strip()
        if not text:
            raise RuntimeError("Text model returned an empty prompt.")
        return text

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
