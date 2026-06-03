"""Platform-level configuration.

This module holds *platform* settings — model IDs, font paths, API-key loading
and local cache locations. Per-tenant data (brand colours, contact details,
logos, system prompts) lives in Supabase, NOT here.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
ROOT = Path(__file__).resolve().parents[2]  # repo root (img_bot/)
DATA_DIR = ROOT / "data"  # local cache mirror (gitignored)
TENANTS_CACHE = DATA_DIR / "tenants"  # data/tenants/<phone>/{logo.png, posters/...}

# --------------------------------------------------------------------------- #
# Models
# --------------------------------------------------------------------------- #
# Claude: Opus for the one-time onboarding system-prompt build (quality first),
# Sonnet for runtime expansion (called per poster — cost matters more).
CLAUDE_ONBOARDING_MODEL = "claude-sonnet-4-6"
CLAUDE_RUNTIME_MODEL = "claude-sonnet-4-6"

# Gemini image model — handles the actual rendering.
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image-preview"

# --------------------------------------------------------------------------- #
# Supabase — all app tables live under this schema (NOT public). Must be added
# to "Exposed schemas" in the Supabase dashboard (Project Settings → API) so
# PostgREST will route to it.
# --------------------------------------------------------------------------- #
SUPABASE_SCHEMA = "img_bot"

# --------------------------------------------------------------------------- #
# Fonts (OS-dependent)
# --------------------------------------------------------------------------- #
_IS_LINUX = sys.platform.startswith("linux")

if _IS_LINUX:
    # Ubuntu / Debian: `apt install fonts-noto fonts-liberation`
    DEFAULT_HINDI_FONT = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    DEFAULT_HINDI_FONT_INDEX = 0
    DEFAULT_LATIN_FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
else:
    DEFAULT_HINDI_FONT = "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"
    DEFAULT_HINDI_FONT_INDEX = 1  # 0 = Regular, 1 = Bold
    DEFAULT_LATIN_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# --------------------------------------------------------------------------- #
# Defaults for tenant theme (used when onboarding metadata omits a field)
# --------------------------------------------------------------------------- #
DEFAULT_THEME = {
    "header_bg": "#5e1622",
    "header_accent": "#c8a24a",
    "header_text": "#f6efe1",
    "footer_bg": "#5e1622",
    "footer_top_line": "#c8a24a",
    "footer_text": "#f6efe1",
    "header_height_ratio": 0.12,
    "footer_height_ratio": 0.12,
    "header_logo_height_ratio": 1.30,
    "language": "en",  # "en" or "hi" — chooses Latin vs Hindi font for header
}


# --------------------------------------------------------------------------- #
# Secrets / env
# --------------------------------------------------------------------------- #
def load_env() -> None:
    """Load `.env` from the repo root. Idempotent — call from any entry point."""
    load_dotenv(ROOT / ".env")


def _require(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise RuntimeError(f"{name} is not set. Add it to .env or the environment.")
    return val


def gemini_key() -> str:
    return _require("GEMINI_API_KEY")


def anthropic_key() -> str:
    return _require("ANTHROPIC_API_KEY")


def supabase_url() -> str:
    return _require("SUPABASE_URL")


def supabase_service_key() -> str:
    return _require("SUPABASE_SERVICE_KEY")
