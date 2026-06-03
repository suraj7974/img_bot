"""Gemini image-generation client.

A thin wrapper around `google-genai` exposing one call: take a detailed image
prompt, return raw PNG bytes. The text expansion step that used to live here
has moved to `imgbot.ai.claude` since Claude now drives the brain of the
pipeline.
"""

from __future__ import annotations

from google import genai

from imgbot import config


class GeminiImageClient:
    """Thin wrapper around `google-genai` for the image-rendering step."""

    def __init__(self, api_key: str | None = None):
        config.load_env()
        key = api_key or config.gemini_key()
        self._client = genai.Client(api_key=key)

    def generate_image(self, prompt: str) -> bytes:
        """Render `prompt` into a poster and return the first image's bytes."""
        response = self._client.models.generate_content(
            model=config.GEMINI_IMAGE_MODEL,
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
