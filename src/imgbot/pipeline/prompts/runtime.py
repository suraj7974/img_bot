"""Runtime user-message template for `ClaudeClient.expand_to_image_prompt`.

The per-tenant system prompt does the heavy lifting (brand voice, palette,
zones, output shape, **plus the trend awareness baked in at onboarding via
web search**). This user message just delivers the small piece of per-call
context: today's date and the rolling list of recent idea titles to avoid
repeating. Keeping it short keeps the bytes after the cached system block
small and cheap.
"""

from __future__ import annotations


RUNTIME_USER_PROMPT = """Today's date is {today}.

Recent posters this tenant has already produced (do NOT repeat any of these topics — pick something distinct):

{recent_idea_titles}

Pick ONE fresh idea on-brand for this tenant. Roughly 6-7 of every 10 generations should lean into the festivals, seasonal beats, or trending moments described in your system instructions, choosing whichever is closest to today's date. The remaining 3-4 can be evergreen brand content. Use the recent-posters list to decide which side of that ratio today should fall on — if the last few were all evergreen, lean trend; if the last few were all trend, do an evergreen. Never repeat a recent topic.

Then emit your output through the `emit_poster_plan` tool: a short idea title and a full, dense, self-contained detailed image-generation prompt that follows every rule in your system instructions.
"""
