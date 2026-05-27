"""Central configuration for the poster pipeline.

Edit the values here to tweak models, branding text, colours and layout.
Nothing else in the codebase hard-codes these.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parent

# ----------------------------------------------------------------------------
# Gemini models
# ----------------------------------------------------------------------------
TEXT_MODEL = "gemini-2.5-pro"          # step 1: query -> detailed image prompt
IMAGE_MODEL = "gemini-3.1-flash-image-preview"  # step 2: prompt -> generated poster

# How many design variants to produce per query. The text model returns this
# many prompts (same data, different design); each becomes its own poster.
NUM_VARIANTS = 2

# ----------------------------------------------------------------------------
# Files / folders
# ----------------------------------------------------------------------------
LOGO_PATH = ROOT / "police-logo.png"
OUTPUT_DIR = ROOT / "output"

# ----------------------------------------------------------------------------
# Branding text
# ----------------------------------------------------------------------------
DEPARTMENT_NAME = "महासमुंद पुलिस"   # header — centred between the two logos
SOCIAL_HANDLE = "/Mahasamundpolice"
CONTROL_ROOM_TEXT = "कंट्रोल रूम नं. - 9479229939"

# ----------------------------------------------------------------------------
# Layout ratios
# ----------------------------------------------------------------------------
# Header band is PREPENDED above the image (the canvas is extended upward), and
# the footer band is APPENDED below it. Both are separate strips, so nothing on
# the original generated poster is ever covered or cut.
HEADER_HEIGHT_RATIO = 0.11     # prepended band height as a fraction of image height
HEADER_LOGO_HEIGHT_RATIO = 1.56  # logo height as a fraction of the header band height
FOOTER_HEIGHT_RATIO = 0.07     # appended band height as a fraction of image height

# The logo already ships with a transparent background, so no flood-fill is
# needed. Set this True only if you swap in a logo with a solid white backdrop.
LOGO_REMOVE_BG = False
LOGO_BG_THRESH = 45         # colour tolerance for the white-background removal

# ----------------------------------------------------------------------------
# Band colours (header + footer share the same palette)
# ----------------------------------------------------------------------------
HEADER_BG = (26, 56, 53)          # dark teal band (matches footer)
HEADER_ACCENT_LINE = (181, 161, 78)  # olive/gold accent line under the header
HEADER_TEXT = (255, 255, 255)     # white department name
FOOTER_BG = (26, 56, 53)          # dark teal band
FOOTER_TOP_LINE = (181, 161, 78)  # olive/gold accent line on top of the band
FOOTER_TEXT = (255, 255, 255)     # white text + icons

# ----------------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------------
HINDI_FONT = "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"
HINDI_FONT_INDEX = 1   # 0 = Regular, 1 = Bold
LATIN_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
