"""Compose tenant branding onto a generated poster — blended overlay style.

The output is the SAME size as the input image (no canvas extension). We:

  * paste the tenant logo at the top-centre of the image, transparent — it
    blends with whatever the AI rendered behind it
  * blend a translucent rounded "pill" near the bottom that holds the
    contact info on a single line, every text at the SAME font size, with a
    subtle outline matching the tenant accent colour

Everything is tenant-driven via `Theme` + `BrandIdentity` — there is no module
state. The function is pure given (image_bytes, theme, brand, logo_bytes).
"""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from imgbot import config
from imgbot.tenants.schema import BrandIdentity, Theme, hex_to_rgb


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
def _hindi_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        config.DEFAULT_HINDI_FONT, size,
        index=config.DEFAULT_HINDI_FONT_INDEX,
        layout_engine=ImageFont.Layout.RAQM,
    )


def _latin_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(config.DEFAULT_LATIN_FONT, size)


def _header_font(size: int, language: str) -> ImageFont.FreeTypeFont:
    return _hindi_font(size) if language == "hi" else _latin_font(size)


# --------------------------------------------------------------------------- #
# Logo
# --------------------------------------------------------------------------- #
def _load_logo(logo_bytes: bytes, remove_white_bg: bool = False) -> Image.Image:
    """Decode the logo as RGBA. Optionally flood-fill a near-white background
    to transparent (for legacy logos without an alpha channel)."""
    logo = Image.open(io.BytesIO(logo_bytes)).convert("RGBA")
    if not remove_white_bg:
        return logo

    rgb = logo.convert("RGB")
    sentinel = (255, 0, 255)
    w, h = rgb.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(rgb, corner, sentinel, thresh=45)
    alpha = [0 if px == sentinel else 255 for px in rgb.getdata()]
    mask = Image.new("L", rgb.size)
    mask.putdata(alpha)
    logo.putalpha(mask)
    return logo


# --------------------------------------------------------------------------- #
# Header band — small solid strip ABOVE the AI image, holds the logo alone
# --------------------------------------------------------------------------- #
def _prepend_header(base: Image.Image, theme: Theme, brand: BrandIdentity,
                    logo: Image.Image) -> Image.Image:
    """Return a taller canvas: a thin solid band on top, the AI image below.

    The logo sits inside that band with no backdrop pill around it — it's
    alone on a solid theme colour. The AI image is untouched, so there's
    zero risk of the logo overlapping ornament, headlines or hero subjects
    no matter what the AI rendered.

    Band height is computed from the logo size + breathing room (plus the
    optional `dept_name` text if set), so the strip is as compact as it can
    be while still feeling intentional.
    """
    W, H = base.size

    target_h = max(64, int(H * 0.085))
    target_w = int(logo.width * target_h / logo.height)
    logo_scaled = logo.resize((target_w, target_h), Image.LANCZOS)

    pad_top = max(14, int(target_h * 0.22))
    pad_bot = max(10, int(target_h * 0.18))

    # If the tenant has a dept_name, render it below the logo and grow the band.
    name_text = (brand.dept_name or "").strip() or None
    name_font = None
    name_h = 0
    name_gap = 0
    if name_text:
        name_font = _header_font(max(18, int(H * 0.022)), theme.language)
        d_measure = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        nb = d_measure.textbbox((0, 0), name_text, font=name_font)
        name_h = nb[3] - nb[1]
        name_gap = max(6, int(target_h * 0.10))

    band_h = pad_top + target_h + name_gap + name_h + pad_bot

    color_bg = hex_to_rgb(theme.header_bg)
    color_accent = hex_to_rgb(theme.header_accent)
    color_text = hex_to_rgb(theme.header_text)

    canvas = Image.new("RGBA", (W, H + band_h), color_bg + (255,))
    canvas.paste(base, (0, band_h))

    # Thin accent line along the bottom edge of the band.
    d = ImageDraw.Draw(canvas)
    line_h = max(2, band_h // 30)
    d.rectangle([0, band_h - line_h, W, band_h], fill=color_accent)

    # Centred logo in the band.
    lx = (W - target_w) // 2
    ly = pad_top
    canvas.paste(logo_scaled, (lx, ly), logo_scaled)

    # Optional dept_name centred below the logo, inside the band.
    if name_text:
        nb = d.textbbox((0, 0), name_text, font=name_font)
        nw = nb[2] - nb[0]
        tx = (W - nw) // 2 - nb[0]
        ty = ly + target_h + name_gap - nb[1]
        d.text((tx, ty), name_text, font=name_font, fill=color_text)

    return canvas


# --------------------------------------------------------------------------- #
# Footer — social glyphs drawn as simple white line icons
# --------------------------------------------------------------------------- #
def _draw_instagram(d: ImageDraw.ImageDraw, x: int, y: int, s: int, color) -> None:
    lw = max(2, s // 12)
    r = s // 5
    d.rounded_rectangle([x, y, x + s, y + s], radius=r, outline=color, width=lw)
    c = s // 2
    cr = s // 4
    d.ellipse([x + c - cr, y + c - cr, x + c + cr, y + c + cr], outline=color, width=lw)
    dot = max(2, s // 12)
    dx, dy = x + s - int(s * 0.26), y + int(s * 0.18)
    d.ellipse([dx, dy, dx + dot, dy + dot], fill=color)


def _draw_facebook(d: ImageDraw.ImageDraw, x: int, y: int, s: int, color) -> None:
    lw = max(2, s // 12)
    d.ellipse([x, y, x + s, y + s], outline=color, width=lw)
    _centered_glyph(d, "f", x, y, s, _latin_font(int(s * 0.78)), color)


def _draw_x(d: ImageDraw.ImageDraw, x: int, y: int, s: int, color) -> None:
    _centered_glyph(d, "X", x, y, s, _latin_font(int(s * 0.95)), color)


def _centered_glyph(d, ch, x, y, s, font, color) -> None:
    bbox = d.textbbox((0, 0), ch, font=font)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((x + (s - gw) / 2 - bbox[0], y + (s - gh) / 2 - bbox[1]), ch, font=font, fill=color)


def _overlay_footer(base: Image.Image, theme: Theme, brand: BrandIdentity) -> None:
    """In-place: blend a translucent rounded pill near the bottom of `base`.

    The pill carries every footer string (social handle, phone, email, website)
    on ONE line at the SAME font size, separated by a thin divider. Font size
    auto-shrinks if the joined text would overflow the pill's max width, so
    long lists still fit cleanly. The pill background is translucent so the
    image bleeds through behind it.
    """
    W, H = base.size

    contacts = [
        s for s in (
            brand.social_handle,
            brand.footer_phone,
            brand.footer_email,
            brand.footer_website,
        ) if s and s.strip()
    ]
    if not contacts:
        return

    color_bg = hex_to_rgb(theme.footer_bg)
    color_text = hex_to_rgb(theme.footer_text)
    color_accent = hex_to_rgb(theme.footer_top_line)

    sep = "   ·   "
    full_text = sep.join(contacts)

    # Auto-fit: shrink the font until the joined text fits the pill's max width.
    pad_x_ratio = 0.04
    max_text_w = int(W * (1.0 - 2 * pad_x_ratio - 0.03))  # leave ~3% breathing room
    font_size = max(18, int(H * 0.022))
    d_measure = ImageDraw.Draw(base)
    font = _latin_font(font_size)
    text_bbox = d_measure.textbbox((0, 0), full_text, font=font)
    while text_bbox[2] - text_bbox[0] > max_text_w and font_size > 12:
        font_size -= 1
        font = _latin_font(font_size)
        text_bbox = d_measure.textbbox((0, 0), full_text, font=font)

    text_w = text_bbox[2] - text_bbox[0]
    text_h = text_bbox[3] - text_bbox[1]
    pad_x = int(W * pad_x_ratio)
    pad_y = max(int(text_h * 0.7), 14)
    pill_w = min(text_w + 2 * pad_x, int(W * 0.94))
    pill_h = text_h + 2 * pad_y
    pill_x = (W - pill_w) // 2
    # 6% breathing room below the pill so it never kisses the image edge.
    pill_y = H - pill_h - int(H * 0.06)

    # Translucent pill on its own alpha layer, then composited into base.
    overlay = Image.new("RGBA", base.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle(
        [pill_x, pill_y, pill_x + pill_w, pill_y + pill_h],
        radius=pill_h // 2,
        fill=color_bg + (250,),
        outline=color_accent + (255,),
        width=max(1, int(H * 0.0018)),
    )
    base.alpha_composite(overlay)

    # Text drawn directly on base (opaque). Centre-aligned in the pill.
    d = ImageDraw.Draw(base)
    tx = (W - text_w) // 2 - text_bbox[0]
    ty = pill_y + (pill_h - text_h) // 2 - text_bbox[1]
    d.text((tx, ty), full_text, font=font, fill=color_text)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def add_branding(image_bytes: bytes, theme: Theme, brand: BrandIdentity,
                 logo_bytes: bytes, *, remove_white_bg: bool = False) -> Image.Image:
    """Frame `image_bytes` with the tenant's branding.

      * Header: a thin solid band ABOVE the AI image carrying the logo alone
        (no backdrop pill). The AI image is never covered, so the logo can
        never overlap whatever the AI rendered.
      * Footer: a translucent rounded pill BLENDED onto the bottom of the
        image, holding all contact info on one line at one consistent
        font size.

    Returns an RGB PIL Image ready to save as PNG/JPEG.
    """
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    logo = _load_logo(logo_bytes, remove_white_bg=remove_white_bg)
    canvas = _prepend_header(base, theme, brand, logo)
    _overlay_footer(canvas, theme, brand)
    return canvas.convert("RGB")
