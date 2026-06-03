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
# Phone normalisation — accept "+91...", "91...@c.us", "+91 7974...", etc.
# Store / compare as canonical "+<digits>".
# --------------------------------------------------------------------------- #
_PHONE_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str) -> str:
    """Canonicalise any WhatsApp/E.164-ish input into `+<digits>`.

    Enforces 11-15 digits total — E.164's hard ceiling is 15, and 11 is the
    practical floor once you include a country code (US +1xxx10digits = 11,
    India +91xxxxxxxxxx = 12). This catches the common operator typo of
    omitting the country code (`9876543210` → got 10 digits, missing +91).
    """
    if not raw:
        raise ValueError("phone is empty")
    # Drop the WhatsApp suffix and anything after @, then strip non-digits.
    head = raw.split("@", 1)[0]
    digits = _PHONE_DIGITS.sub("", head)
    if not digits:
        raise ValueError(f"no digits in phone: {raw!r}")
    if len(digits) < 11 or len(digits) > 15:
        raise ValueError(
            f"phone has {len(digits)} digits; expected 11-15 (E.164 with country code). "
            f"For Indian numbers use +91 followed by the 10-digit mobile, "
            f"e.g. +917974387273. Got {raw!r}."
        )
    return "+" + digits


# --------------------------------------------------------------------------- #
# Sub-models
# --------------------------------------------------------------------------- #
class BusinessInfo(BaseModel):
    name: str
    type: str  # free text, e.g. "event management", "sweet shop", "coaching institute"
    location: Optional[str] = None
    tagline: Optional[str] = None
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
    """Colour palette and band geometry for header + footer."""
    header_bg: HexColor = "#5e1622"
    header_accent: HexColor = "#c8a24a"
    header_text: HexColor = "#f6efe1"
    footer_bg: HexColor = "#5e1622"
    footer_top_line: HexColor = "#c8a24a"
    footer_text: HexColor = "#f6efe1"
    header_height_ratio: float = 0.12
    footer_height_ratio: float = 0.12
    header_logo_height_ratio: float = 1.30  # logo can exceed the band (overlaps below)
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
    phone: str
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
