"""Runtime user-message template for `ClaudeClient.expand_to_image_prompt`.

The per-tenant system prompt does ALL the heavy lifting — brand voice, palette,
zones, output shape, freshness / trends contract, business-relevance rules.
This user message just delivers two pieces of per-call context:

  * today's date
  * the rolling list of recent idea titles to avoid repeating

Trend mechanics (windows, ratios, social-media awareness) are deferred to a
phase-2 design and currently live entirely inside the cached system prompt.
Keeping this user turn short keeps the bytes after the cached system block
small and the per-call cost minimal.
"""

from __future__ import annotations


RUNTIME_USER_PROMPT = """Today's date is {today}.

Recent posters this tenant has already produced — do NOT repeat or near-duplicate any of these topics:

{recent_idea_titles}

Pick ONE fresh idea on-brand for this tenant, following every rule in your system instructions. Then emit your output through the `emit_poster_plan` tool: a short idea title (≤8 words) and a full, dense, self-contained detailed image-generation prompt.
"""
