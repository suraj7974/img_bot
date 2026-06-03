"""Claude wrapper for the imgbot pipeline.

Two calls:

  * build_system_prompt — one-time per tenant, during onboarding. Uses Opus 4.8
    with vision: reads the tenant's metadata + sample posters + a couple of
    bundled reference examples and emits a new per-tenant system prompt that
    drives every future generation for that tenant.
  * expand_to_image_prompt — runtime, per generation. Uses Sonnet 4.6 with the
    cached per-tenant system prompt and forced JSON output (tool-use) to emit
    `{idea_title, detailed_prompt}`. Diversity is steered by feeding recent
    idea titles into the user message; freshness by feeding today's date.
"""

from __future__ import annotations

import base64
import io
import json
from datetime import date

from anthropic import Anthropic
from PIL import Image

from imgbot import config
from imgbot.onboarding import meta_prompts
from imgbot.pipeline.prompts import runtime as runtime_prompts


def _detect_image_media_type(image_bytes: bytes) -> str:
    """Sniff the format so the API sees the right media type."""
    fmt = (Image.open(io.BytesIO(image_bytes)).format or "").upper()
    return {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "JPG": "image/jpeg",
        "WEBP": "image/webp",
        "GIF": "image/gif",
    }.get(fmt, "image/png")


def _image_block(image_bytes: bytes) -> dict:
    return {
        "type": "image",
        "source": {
            "type": "base64",
            "media_type": _detect_image_media_type(image_bytes),
            "data": base64.b64encode(image_bytes).decode("ascii"),
        },
    }


class ClaudeClient:
    """Thin Anthropic wrapper for the two pipeline brain steps."""

    def __init__(self, api_key: str | None = None):
        config.load_env()
        self._client = Anthropic(api_key=api_key or config.anthropic_key())

    # ------------------------------------------------------------------ #
    # Onboarding: tenant metadata + sample posters → per-tenant system prompt
    # ------------------------------------------------------------------ #
    def build_system_prompt(
        self,
        meta_json: dict,
        sample_images: list[bytes] | None = None,
        inspiration_ideas: str | None = None,
    ) -> str:
        """One-time call per tenant. Returns the tailored system prompt text.

        Parameters
        ----------
        meta_json
            JSON-serializable dict of the structured metadata (business / brand /
            theme + quota + notes).
        sample_images
            Optional reference posters Claude looks at via vision. Style cues only.
        inspiration_ideas
            Optional operator-supplied free-text ("what kind of posters do you
            want?"). Style / audience / tone guidance — not facts to invent.

        Sonnet 4.6, no thinking, medium effort, forced tool output. Bounded to
        one call (~$0.05–0.10) — earlier Opus + adaptive thinking + web_search
        + pause_turn loop combo could run for 15 min and cost $1+ per onboarding.
        """
        sample_images = sample_images or []
        user_blocks: list[dict] = [
            {"type": "text", "text": meta_prompts.ONBOARDING_INSTRUCTIONS},
        ]

        for name, body in meta_prompts.REFERENCE_EXAMPLES:
            user_blocks.append({
                "type": "text",
                "text": f"\n\n=== REFERENCE EXAMPLE: {name} ===\n\n{body}",
            })

        user_blocks.append({
            "type": "text",
            "text": "\n\n=== TENANT METADATA (JSON) ===\n\n"
                    + json.dumps(meta_json, indent=2, ensure_ascii=False),
        })

        if inspiration_ideas and inspiration_ideas.strip():
            user_blocks.append({
                "type": "text",
                "text": "\n\n=== TENANT INSPIRATION / IDEAS (style guidance, NOT facts) ===\n\n"
                        + inspiration_ideas.strip(),
            })

        if sample_images:
            user_blocks.append({
                "type": "text",
                "text": "\n\n=== TENANT SAMPLE POSTERS (style + content reference) ===",
            })
            user_blocks.extend(_image_block(b) for b in sample_images)

        user_blocks.append({"type": "text", "text": meta_prompts.ONBOARDING_FINAL_CUE})

        # Force the output through a tool so the parsed result is GUARANTEED
        # to be just the prompt text — no preamble, no "here's the prompt:"
        # narration leaking into the saved system_prompt column.
        tool = {
            "name": "emit_system_prompt",
            "description": (
                "Emit the complete per-tenant SYSTEM PROMPT as a single string. "
                "This string is stored verbatim and used as the system block on every "
                "future runtime call for this tenant."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "system_prompt": {
                        "type": "string",
                        "description": (
                            "The complete per-tenant system prompt text, ready to ship "
                            "verbatim to the runtime model. No markdown fences, no "
                            "commentary, no 'here is the prompt:' framing — just the "
                            "prompt body itself."
                        ),
                    },
                },
                "required": ["system_prompt"],
            },
        }

        # One bounded call. No server tools, no thinking, forced tool_choice for
        # clean parsing. Festivals / seasonal moments come from Claude's training
        # knowledge (cutoff Jan 2026 covers all of 2026 fine).
        response = self._client.messages.create(
            model=config.CLAUDE_ONBOARDING_MODEL,
            max_tokens=8000,
            thinking={"type": "disabled"},
            output_config={"effort": "medium"},
            system=meta_prompts.ONBOARDING_SYSTEM,
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit_system_prompt"},
            messages=[{"role": "user", "content": user_blocks}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "emit_system_prompt":
                prompt = block.input.get("system_prompt", "").strip()
                if not prompt:
                    raise RuntimeError("emit_system_prompt tool was called with empty content.")
                return prompt
        raise RuntimeError("Claude did not invoke the emit_system_prompt tool.")

    # ------------------------------------------------------------------ #
    # Runtime: system_prompt + history + date → {idea_title, detailed_prompt}
    # ------------------------------------------------------------------ #
    def expand_to_image_prompt(
        self,
        tenant_system_prompt: str,
        recent_idea_titles: list[str],
        today: date,
    ) -> dict:
        """Per-generation call. Returns `{"idea_title": str, "detailed_prompt": str}`.

        The per-tenant system prompt is the largest stable piece — we cache it
        via `cache_control: ephemeral` so a burst of generations for the same
        tenant pays ~0.1× for that block on every call after the first.
        """
        tool = {
            "name": "emit_poster_plan",
            "description": (
                "Emit one fresh poster plan: a short idea title and the full "
                "detailed image-generation prompt the rendering model will use."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "idea_title": {
                        "type": "string",
                        "description": (
                            "Short (≤8 words) human-readable title for this poster idea. "
                            "Shown as a WhatsApp caption and used as history in future "
                            "calls to avoid repeating topics."
                        ),
                    },
                    "detailed_prompt": {
                        "type": "string",
                        "description": (
                            "Self-contained, dense image-generation prompt — the literal "
                            "text the image model will receive. Must follow the tenant "
                            "system prompt's structural rules (zones, palette, language)."
                        ),
                    },
                },
                "required": ["idea_title", "detailed_prompt"],
            },
        }

        history_block = (
            "\n".join(f"- {t}" for t in recent_idea_titles)
            if recent_idea_titles
            else "(no prior posters yet — first generation for this tenant)"
        )
        user_text = runtime_prompts.RUNTIME_USER_PROMPT.format(
            recent_idea_titles=history_block,
            today=today.isoformat(),
        )

        # Anthropic 400s if adaptive thinking is combined with forced
        # tool_choice. We need forced tool_choice so the output is guaranteed
        # parseable, so thinking stays off here. Effort still controls how
        # carefully the model reasons inline.
        response = self._client.messages.create(
            model=config.CLAUDE_RUNTIME_MODEL,
            max_tokens=8192,
            thinking={"type": "disabled"},
            output_config={"effort": "high"},
            system=[{
                "type": "text",
                "text": tenant_system_prompt,
                "cache_control": {"type": "ephemeral"},
            }],
            tools=[tool],
            tool_choice={"type": "tool", "name": "emit_poster_plan"},
            messages=[{"role": "user", "content": user_text}],
        )

        for block in response.content:
            if block.type == "tool_use" and block.name == "emit_poster_plan":
                plan = dict(block.input)
                if "idea_title" not in plan or "detailed_prompt" not in plan:
                    raise RuntimeError(f"Tool emitted incomplete plan: {plan!r}")
                return plan

        raise RuntimeError("Claude did not invoke the emit_poster_plan tool.")
