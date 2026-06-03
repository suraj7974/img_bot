"""Compose a tenant-branded header + footer onto a generated poster.

  * Header: a coloured band PREPENDED above the image (canvas extended upward),
    with the tenant logo on the far left and far right and the tenant's display
    name (`brand.dept_name`) centred between them. Nothing on the original
    poster is covered or cut.
  * Footer: a coloured band APPENDED below the image with an accent line on
    top, social glyphs + handle on the left, and the tenant's stacked contact
    lines (phone / email / website) on the right. Header and footer share the
    same palette by convention.

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
# Header
# --------------------------------------------------------------------------- #
def _prepend_header(base: Image.Image, theme: Theme, brand: BrandIdentity,
                    logo: Image.Image) -> Image.Image:
    """Return a taller canvas: header band on top, original image below."""
    W, H = base.size
    band_h = int(H * theme.header_height_ratio)

    canvas = Image.new("RGBA", (W, H + band_h), hex_to_rgb(theme.header_bg) + (255,))
    canvas.paste(base, (0, band_h))
    d = ImageDraw.Draw(canvas)

    # Accent line along the bottom edge of the header band.
    line_h = max(2, band_h // 20)
    d.rectangle([0, band_h - line_h, W, band_h], fill=hex_to_rgb(theme.header_accent))

    # Two logos: far left and far right.
    target_h = int(band_h * theme.header_logo_height_ratio)
    target_w = int(logo.width * target_h / logo.height)
    logo_scaled = logo.resize((target_w, target_h), Image.LANCZOS)
    pad = int(W * 0.03)
    # Lower the logos so they dip over the accent line into the image below.
    ly = (band_h - target_h) // 2 + int(band_h * 0.22)
    canvas.paste(logo_scaled, (pad, ly), logo_scaled)                    # left
    canvas.paste(logo_scaled, (W - pad - target_w, ly), logo_scaled)     # right

    # Optional centre text (business name / tagline). Skip entirely when
    # blank — the header renders as a clean logos-only strip.
    if brand.dept_name and brand.dept_name.strip():
        name_font = _header_font(int(band_h * 0.55), theme.language)
        nb = d.textbbox((0, 0), brand.dept_name, font=name_font)
        nw = nb[2] - nb[0]
        d.text(((W - nw) / 2 - nb[0], band_h / 2 - (nb[3] - nb[1]) / 2 - nb[1]),
               brand.dept_name, font=name_font, fill=hex_to_rgb(theme.header_text))

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


def _append_footer(base: Image.Image, theme: Theme, brand: BrandIdentity) -> Image.Image:
    """Return a taller canvas: image on top, footer band appended below."""
    W, H = base.size
    band_h = int(H * theme.footer_height_ratio)

    canvas = Image.new("RGBA", (W, H + band_h), hex_to_rgb(theme.footer_bg) + (255,))
    canvas.paste(base, (0, 0))
    d = ImageDraw.Draw(canvas)

    top = H
    line_h = max(2, band_h // 20)
    d.rectangle([0, top, W, top + line_h], fill=hex_to_rgb(theme.footer_top_line))

    pad = int(W * 0.022)
    color = hex_to_rgb(theme.footer_text)
    cy = top + band_h // 2

    # ---- Left: social glyphs + handle (if any) ----
    icon = int(band_h * 0.42)
    gap = int(icon * 0.32)
    iy = cy - icon // 2
    x = pad
    _draw_instagram(d, x, iy, icon, color); x += icon + gap
    _draw_facebook(d, x, iy, icon, color);  x += icon + gap
    _draw_x(d, x, iy, icon, color);          x += icon + int(gap * 1.4)

    if brand.social_handle:
        handle_font = _latin_font(int(band_h * 0.30))
        hb = d.textbbox((0, 0), brand.social_handle, font=handle_font)
        d.text((x, cy - (hb[3] - hb[1]) / 2 - hb[1]), brand.social_handle,
               font=handle_font, fill=color)

    # ---- Right: stacked contact lines (skip blank ones) ----
    contact_lines = [s for s in (brand.footer_phone, brand.footer_email, brand.footer_website) if s]
    if contact_lines:
        contact_font = _latin_font(int(band_h * 0.18))
        line_gap = int(band_h * 0.06)
        bboxes = [d.textbbox((0, 0), s, font=contact_font) for s in contact_lines]
        heights = [b[3] - b[1] for b in bboxes]
        block_h = sum(heights) + line_gap * (len(contact_lines) - 1)
        y = cy - block_h // 2
        for s, b, h in zip(contact_lines, bboxes, heights):
            cw = b[2] - b[0]
            d.text((W - pad - cw - b[0], y - b[1]), s, font=contact_font, fill=color)
            y += h + line_gap

    return canvas


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def add_branding(image_bytes: bytes, theme: Theme, brand: BrandIdentity,
                 logo_bytes: bytes, *, remove_white_bg: bool = False) -> Image.Image:
    """Frame `image_bytes` with the tenant's header + footer bands.

    Returns an RGB PIL Image ready to save as PNG/JPEG.
    """
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    logo = _load_logo(logo_bytes, remove_white_bg=remove_white_bg)
    with_header = _prepend_header(base, theme, brand, logo)
    branded = _append_footer(with_header, theme, brand)
    return branded.convert("RGB")
