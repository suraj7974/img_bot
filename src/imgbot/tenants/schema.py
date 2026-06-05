"""Pydantic models for tenant data.

A `Tenant` is one paying customer. It carries the business profile, the brand
identity (visible names + contact lines), a theme (colours/ratios for the
header/footer bands), a Supabase-stored logo, the Claude-generated per-tenant
system prompt, and quota state.

Onboarding consumes a `TenantMetaInput` (loaded from yaml). The runtime side
deals with a hydrated `Tenant` fetched from Supabase.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Annotated, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, Field, field_validator


HexColor = Annotated[str, Field(pattern=r"^#[0-9A-Fa-f]{6}$")]
Language = Literal["en", "hi"]


def hex_to_rgb(h: str) -> tuple[int, int, int]:
    """`#RRGGBB` → `(r, g, b)`."""
    h = h.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


# --------------------------------------------------------------------------- #
# Phone & chat-ID normalisation.
#
# `phone` is the admin-typed canonical identifier (E.164 like "+917974387273").
# `chat_id` is the opaque WhatsApp JID (`<digits>@c.us` or `<digits>@lid`) that
# the bot auto-resolves on first contact via `client.getNumberId(phone)`.
#
# Both are stored on the tenant row. Lookups prefer chat_id (exact match
# against `message.from`) and fall back to phone.
# --------------------------------------------------------------------------- #
_NON_DIGITS = re.compile(r"\D+")
_ALLOWED_SERVERS = ("c.us", "lid")
DEFAULT_COUNTRY_CODE = "91"  # India. If the admin types a bare 10-digit number, prepend +91.


def normalize_phone(raw: str) -> str:
    """Return canonical E.164 (`+<digits>`).

    Accepts:
      * `+917974387273` — already canonical, used as-is
      * `917974387273`  — already has country code, just prepends `+`
      * `7974387273`    — 10-digit Indian mobile, auto-prepended with `+91`
      * `+91 7974 387 273`, `+91-79743-87273`, etc. — formatting stripped

    Enforces a final length of 11–15 digits (E.164's hard ceiling is 15).
    """
    if raw is None or not str(raw).strip():
        raise ValueError("phone is empty")
    raw = str(raw).strip()

    digits = _NON_DIGITS.sub("", raw)
    if not digits:
        raise ValueError(f"phone has no digits: {raw!r}")

    # If admin gave 10 digits (the common Indian mobile shape with no country
    # code), prepend the default country code. Don't touch anything longer or
    # starting with `+` — they presumably already know what they're doing.
    if not raw.startswith("+") and len(digits) == 10:
        digits = DEFAULT_COUNTRY_CODE + digits

    if len(digits) < 11 or len(digits) > 15:
        raise ValueError(
            f"phone has {len(digits)} digits; expected 11-15 (E.164 with country code). "
            f"For Indian numbers use 10 digits (auto-prefixed +91) or +<country><number>. "
            f"Got {raw!r}."
        )
    return "+" + digits


def normalize_chat_id(raw: str) -> str:
    """Return a canonical WhatsApp JID (`<digits>@c.us` or `<digits>@lid`).

    Used for the chat_id field (resolved by the bot, not user-typed). Accepts
    only full JID strings — no bare-phone fallback to keep the two ids clearly
    distinct in the codebase.
    """
    if raw is None or not str(raw).strip():
        raise ValueError("chat_id is empty")
    raw = str(raw).strip().lower()
    if "@" not in raw:
        raise ValueError(
            f"chat_id must be a WhatsApp JID like `<digits>@c.us` or "
            f"`<digits>@lid`; got {raw!r}"
        )
    user, _, server = raw.rpartition("@")
    digits = _NON_DIGITS.sub("", user)
    if not digits:
        raise ValueError(f"chat_id has no user digits: {raw!r}")
    if server not in _ALLOWED_SERVERS:
        raise ValueError(
            f"chat_id has unsupported server '@{server}'; expected "
            f"@c.us or @lid. Got {raw!r}."
        )
    return f"{digits}@{server}"


def derived_chat_id(phone: str) -> str:
    """Best-effort `phone -> chat_id` for non-@lid accounts.

    Phone-based WhatsApp users have chat IDs that are literally the phone
    digits + `@c.us`. We can compute it offline — no API call needed — and use
    it as the initial value when the bot hasn't yet seen the user. If the
    account is @lid, `client.getNumberId` on the bot side overwrites this
    with the real LID on first contact.
    """
    phone = normalize_phone(phone)
    return phone.lstrip("+") + "@c.us"


# --------------------------------------------------------------------------- #
# Sub-models
# --------------------------------------------------------------------------- #
class BusinessInfo(BaseModel):
    name: str
    type: str  # free text, e.g. "event management", "sweet shop", "coaching institute"
    location: Optional[str] = None
    language: Language = "en"
    audience: Optional[str] = None  # who the posters target
    tone: Optional[str] = None      # "luxury", "festive", "official"
    notes: Optional[str] = None     # any extra context the operator wants Claude to see


class BrandIdentity(BaseModel):
    """Visible branding strings composited by the pipeline."""
    # Centre of the header band. Optional — when None / empty, the header
    # renders as a logos-only strip with no centre text (cleaner if the
    # tenant doesn't want a tagline or business name at the top).
    dept_name: Optional[str] = None
    social_handle: Optional[str] = None  # next to glyphs in footer left
    footer_phone: Optional[str] = None
    footer_email: Optional[str] = None
    footer_website: Optional[str] = None
    footer_address: Optional[str] = None  # reserved for future use


class Theme(BaseModel):
    """Colour palette and band geometry for header + footer.

    Every colour is OPTIONAL. When set, it's used verbatim. When None, the
    brand compositor samples the AI image's edge and derives a matching
    palette so the bands feel like part of the same scene — no awkward
    maroon strip on a green Diwali poster.
    """
    header_bg: Optional[HexColor] = None
    header_accent: Optional[HexColor] = None
    header_text: Optional[HexColor] = None
    footer_bg: Optional[HexColor] = None
    footer_top_line: Optional[HexColor] = None
    footer_text: Optional[HexColor] = None
    # Band-size ratios are no longer used (bands auto-size to their contents),
    # but the fields stay so existing tenant rows keep validating.
    header_height_ratio: float = 0.12
    footer_height_ratio: float = 0.12
    header_logo_height_ratio: float = 1.30
    language: Language = "en"  # controls header font choice (Latin vs Devanagari)


# --------------------------------------------------------------------------- #
# Input — the structured part of an onboarding submission. Binary assets
# (logo, sample posters) and the free-text `inspiration_ideas` block travel
# alongside this as separate parameters to the orchestrator.
# --------------------------------------------------------------------------- #
class TenantMetaInput(BaseModel):
    """Structured onboarding metadata submitted via the web form."""
    phone: str
    business: BusinessInfo
    brand: BrandIdentity
    theme: Theme = Field(default_factory=Theme)
    plan_quota: int = 10
    notes: Optional[str] = None
    # Free-text "what kind of posters do you want?" — moodboard notes, style
    # cues, audience details, brand inspirations. Claude weaves it into the
    # generated system prompt as style guidance, not as ground-truth facts.
    inspiration_ideas: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)


# --------------------------------------------------------------------------- #
# Persisted records
# --------------------------------------------------------------------------- #
class Tenant(BaseModel):
    """Hydrated tenant row pulled from Supabase."""
    id: UUID
    phone: str                          # E.164, admin-typed, canonical identifier
    chat_id: Optional[str] = None       # WhatsApp JID, auto-resolved by the bot
    business: BusinessInfo
    brand: BrandIdentity
    theme: Theme
    logo_path: str                      # Supabase Storage path
    samples: list[str] = Field(default_factory=list)
    system_prompt: str
    plan_quota: int
    quota_used: int
    quota_period_start: date
    notes: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    @field_validator("phone")
    @classmethod
    def _phone(cls, v: str) -> str:
        return normalize_phone(v)

    @field_validator("chat_id")
    @classmethod
    def _chat_id(cls, v: Optional[str]) -> Optional[str]:
        return normalize_chat_id(v) if v else None

    @property
    def quota_remaining(self) -> int:
        return max(0, self.plan_quota - self.quota_used)


class PosterRecord(BaseModel):
    id: UUID
    tenant_id: UUID
    idea_title: str
    detailed_prompt: str
    image_path: Optional[str] = None
    raw_path: Optional[str] = None
    status: Literal["done", "failed"] = "done"
    error: Optional[str] = None
    created_at: datetime
