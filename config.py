"""Central configuration for the poster pipeline.

Edit the values here to tweak models, branding text, colours and layout.
Nothing else in the codebase hard-codes these.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
_IS_LINUX = sys.platform.startswith("linux")

# ----------------------------------------------------------------------------
# Gemini models
# ----------------------------------------------------------------------------
TEXT_MODEL = "gemini-2.5-pro"  # step 1: query -> detailed image prompt
IMAGE_MODEL = "gemini-3.1-flash-image-preview"  # step 2: prompt -> generated poster

# How many design variants to produce per query. The text model returns this
# many prompts (same data, different design); each becomes its own poster.
NUM_VARIANTS = 1

# ----------------------------------------------------------------------------
# Files / folders
# ----------------------------------------------------------------------------
LOGO_PATH = ROOT / "bastar.png"
OUTPUT_DIR = ROOT / "output"

# ----------------------------------------------------------------------------
# Branding text
# ----------------------------------------------------------------------------
DEPARTMENT_NAME = "Creation with perfection"
SOCIAL_HANDLE = "@baster.event"

# ----------------------------------------------------------------------------
# Layout ratios
# ----------------------------------------------------------------------------
HEADER_HEIGHT_RATIO = 0.12
HEADER_LOGO_HEIGHT_RATIO = 1.30
FOOTER_HEIGHT_RATIO = 0.12

# The logo already ships with a transparent background, so no flood-fill is
# needed. Set this True only if you swap in a logo with a solid white backdrop.
LOGO_REMOVE_BG = False
LOGO_BG_THRESH = 45

# ----------------------------------------------------------------------------
# Band colours (header + footer share the same palette)
# ----------------------------------------------------------------------------
HEADER_BG = (94, 22, 34)  # deep maroon
HEADER_ACCENT_LINE = (200, 162, 74)  # antique gold
HEADER_TEXT = (246, 239, 225)  # cream
FOOTER_BG = (94, 22, 34)
FOOTER_TOP_LINE = (200, 162, 74)
FOOTER_TEXT = (246, 239, 225)

FOOTER_PHONE = "MO. 7974387273"
FOOTER_EMAIL = "Bempl2025@gmail.com"
FOOTER_WEBSITE = "www.basterevent.com"

# ----------------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------------
if _IS_LINUX:
    # Ubuntu: install via `apt install fonts-noto fonts-liberation`.
    HINDI_FONT = "/usr/share/fonts/truetype/noto/NotoSansDevanagari-Bold.ttf"
    HINDI_FONT_INDEX = 0
    LATIN_FONT = "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
else:
    HINDI_FONT = "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"
    HINDI_FONT_INDEX = 1  # 0 = Regular, 1 = Bold
    LATIN_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
