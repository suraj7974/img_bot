"""Step 3 — overlay the police logo (header) and a branded footer band.

  * Header: the police logo, scaled small, pasted into the top-left corner of
    the generated poster (its own transparency is used as the paste mask).
  * Footer: a dark-teal band drawn across the bottom with an olive accent line,
    social glyphs + handle on the left, and the control-room line on the right.
    Hindi text is shaped with the RAQM layout engine for correct conjuncts.
"""

import io

from PIL import Image, ImageDraw, ImageFont

import config


# --------------------------------------------------------------------------- #
# Fonts
# --------------------------------------------------------------------------- #
def _hindi_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(
        config.HINDI_FONT, size,
        index=config.HINDI_FONT_INDEX,
        layout_engine=ImageFont.Layout.RAQM,
    )


def _latin_font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(config.LATIN_FONT, size)


# --------------------------------------------------------------------------- #
# Header
# --------------------------------------------------------------------------- #
def _load_logo() -> Image.Image:
    """Open the logo, flood-filling its near-white background to transparent."""
    logo = Image.open(config.LOGO_PATH).convert("RGBA")
    if not config.LOGO_REMOVE_BG:
        return logo

    rgb = logo.convert("RGB")
    sentinel = (255, 0, 255)
    w, h = rgb.size
    for corner in [(0, 0), (w - 1, 0), (0, h - 1), (w - 1, h - 1)]:
        ImageDraw.floodfill(rgb, corner, sentinel, thresh=config.LOGO_BG_THRESH)
    alpha = [0 if px == sentinel else 255 for px in rgb.getdata()]
    mask = Image.new("L", rgb.size)
    mask.putdata(alpha)
    logo.putalpha(mask)
    return logo


def _paste_logo(base: Image.Image) -> None:
    """Centre the police logo inside the reserved top-left box, in place."""
    logo = _load_logo()

    margin = int(base.width * config.LOGO_MARGIN_RATIO)
    box_w = int(base.width * config.LOGO_BOX_WIDTH_RATIO)
    box_h = int(base.height * config.LOGO_BOX_HEIGHT_RATIO)

    # Scale the logo to fit inside the box (minus padding), keeping aspect.
    avail_w, avail_h = box_w - 2 * margin, box_h - 2 * margin
    scale = min(avail_w / logo.width, avail_h / logo.height)
    lw, lh = max(1, int(logo.width * scale)), max(1, int(logo.height * scale))
    logo = logo.resize((lw, lh), Image.LANCZOS)

    # Centre it within the box (whose origin is the image's top-left corner).
    x = (box_w - lw) // 2
    y = (box_h - lh) // 2
    base.paste(logo, (x, y), logo)


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
    f = _latin_font(int(s * 0.78))
    _centered_glyph(d, "f", x, y, s, f, color)


def _draw_x(d: ImageDraw.ImageDraw, x: int, y: int, s: int, color) -> None:
    f = _latin_font(int(s * 0.95))
    _centered_glyph(d, "X", x, y, s, f, color)


def _centered_glyph(d, ch, x, y, s, font, color) -> None:
    bbox = d.textbbox((0, 0), ch, font=font)
    gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text((x + (s - gw) / 2 - bbox[0], y + (s - gh) / 2 - bbox[1]), ch, font=font, fill=color)


def _append_footer(base: Image.Image) -> Image.Image:
    """Return a taller canvas: the image on top, the footer band appended below."""
    W, H = base.size
    band_h = int(H * config.FOOTER_HEIGHT_RATIO)

    canvas = Image.new("RGBA", (W, H + band_h), config.FOOTER_BG + (255,))
    canvas.paste(base, (0, 0))
    d = ImageDraw.Draw(canvas)

    top = H  # footer begins exactly where the original image ends
    line_h = max(2, band_h // 20)
    d.rectangle([0, top, W, top + line_h], fill=config.FOOTER_TOP_LINE)

    pad = int(W * 0.022)
    color = config.FOOTER_TEXT
    cy = top + band_h // 2  # vertical centre of the band

    # ---- Left: three social glyphs + handle ----
    icon = int(band_h * 0.42)
    gap = int(icon * 0.32)
    iy = cy - icon // 2
    x = pad
    _draw_instagram(d, x, iy, icon, color); x += icon + gap
    _draw_facebook(d, x, iy, icon, color);  x += icon + gap
    _draw_x(d, x, iy, icon, color);          x += icon + int(gap * 1.4)

    handle_font = _latin_font(int(band_h * 0.40))
    hb = d.textbbox((0, 0), config.SOCIAL_HANDLE, font=handle_font)
    d.text((x, cy - (hb[3] - hb[1]) / 2 - hb[1]), config.SOCIAL_HANDLE,
           font=handle_font, fill=color)

    # ---- Right: control-room line (Hindi) ----
    cr_font = _hindi_font(int(band_h * 0.42))
    cb = d.textbbox((0, 0), config.CONTROL_ROOM_TEXT, font=cr_font)
    cw = cb[2] - cb[0]
    d.text((W - pad - cw - cb[0], cy - (cb[3] - cb[1]) / 2 - cb[1]),
           config.CONTROL_ROOM_TEXT, font=cr_font, fill=color)

    return canvas


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #
def add_branding(image_bytes: bytes) -> Image.Image:
    """Overlay the logo on the image and append the footer band below it."""
    base = Image.open(io.BytesIO(image_bytes)).convert("RGBA")
    _paste_logo(base)
    branded = _append_footer(base)
    return branded.convert("RGB")
