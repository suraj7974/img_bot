"""Runtime user-message template for `ClaudeClient.expand_to_image_prompt`.

The per-tenant system prompt does the heavy lifting (brand voice, palette,
zones, output shape). This user message just delivers the small piece of
per-call context: today's date and the list of recent idea titles to avoid
repeating. Keeping it short keeps the bytes after the cached system block
small and cheap.
"""

from __future__ import annotations


RUNTIME_USER_PROMPT = """Today's date is {today}.

Recent posters this tenant has already produced (do NOT repeat any of these topics — pick something distinct):

{recent_idea_titles}

Pick ONE fresh idea on-brand for this tenant (leaning into festivals, cultural moments, or seasonal beats near today's date if relevant), then emit your output through the `emit_poster_plan` tool: a short idea title and a full, dense, self-contained detailed image-generation prompt that follows every rule in your system instructions.
"""
