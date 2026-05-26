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

# ----------------------------------------------------------------------------
# Files / folders
# ----------------------------------------------------------------------------
LOGO_PATH = ROOT / "police-logo.png"
OUTPUT_DIR = ROOT / "output"

# ----------------------------------------------------------------------------
# Branding text
# ----------------------------------------------------------------------------
SOCIAL_HANDLE = "/Mahasamundpolice"
CONTROL_ROOM_TEXT = "कंट्रोल रूम नं. - 9479229939"

# ----------------------------------------------------------------------------
# Layout ratios
# ----------------------------------------------------------------------------
# Logo is centred inside a reserved box in the top-left corner.
LOGO_BOX_WIDTH_RATIO = 0.16    # reserved box width  (fraction of image width)
LOGO_BOX_HEIGHT_RATIO = 0.13   # reserved box height (fraction of image height)
LOGO_MARGIN_RATIO = 0.02       # padding inside the box / from the corner

# Footer band is APPENDED below the image (the canvas is extended downward),
# so nothing on the original poster is ever covered or cut.
FOOTER_HEIGHT_RATIO = 0.07     # appended band height as a fraction of image height

# The logo ships with an opaque near-white background. When True we flood-fill
# that background to transparent so the logo blends onto any poster colour.
LOGO_REMOVE_BG = True
LOGO_BG_THRESH = 45         # colour tolerance for the white-background removal

# ----------------------------------------------------------------------------
# Footer colours
# ----------------------------------------------------------------------------
FOOTER_BG = (26, 56, 53)        # dark teal band
FOOTER_TOP_LINE = (181, 161, 78)  # olive/gold accent line on top of the band
FOOTER_TEXT = (255, 255, 255)   # white text + icons

# ----------------------------------------------------------------------------
# Fonts
# ----------------------------------------------------------------------------
HINDI_FONT = "/System/Library/Fonts/Supplemental/Devanagari Sangam MN.ttc"
HINDI_FONT_INDEX = 1   # 0 = Regular, 1 = Bold
LATIN_FONT = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
