"""Runtime poster pipeline — `(phone) → branded poster`.

Wires up Claude (idea + detailed prompt) → Gemini (image) → compositor (header
+ footer) for one paying tenant. Quota is checked before the expensive calls
and decremented only after a successful save, so a half-failed run doesn't
burn a token.
"""

from __future__ import annotations

import io
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from imgbot.ai.claude import ClaudeClient
from imgbot.ai.gemini import GeminiImageClient
from imgbot.pipeline.brand import add_branding
from imgbot.tenants.assets import AssetStore
from imgbot.tenants.schema import Tenant
from imgbot.tenants.store import TenantStore


class QuotaExceeded(RuntimeError):
    """Tenant has used their monthly quota."""


class TenantNotFound(LookupError):
    """No onboarded tenant for that phone."""


@dataclass
class GenerationResult:
    tenant_id: str
    phone: str
    idea_title: str
    detailed_prompt: str
    final_local_path: Path
    raw_local_path: Path
    final_storage_path: str
    raw_storage_path: str
    quota_used: int
    quota_remaining: int


def _basename(idea_title: str) -> str:
    slug = "_".join(
        "".join(c if c.isalnum() or c in " -_" else " " for c in idea_title).split()
    )[:40] or "poster"
    return f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{slug}"


def run_for_phone(
    phone: str,
    *,
    store: Optional[TenantStore] = None,
    assets: Optional[AssetStore] = None,
    claude: Optional[ClaudeClient] = None,
    gemini: Optional[GeminiImageClient] = None,
    history_n: int = 8,
) -> GenerationResult:
    """End-to-end: resolve tenant → generate → brand → save → bump quota."""
    store = store or TenantStore()
    assets = assets or AssetStore()
    claude = claude or ClaudeClient()
    gemini = gemini or GeminiImageClient()

    tenant: Tenant | None = store.get_by_phone(phone)
    if tenant is None:
        raise TenantNotFound(f"no onboarded tenant for {phone}")

    if tenant.quota_remaining <= 0:
        raise QuotaExceeded(
            f"tenant {tenant.phone} is out of quota "
            f"({tenant.quota_used}/{tenant.plan_quota} used)"
        )

    # ---- Claude: idea + detailed prompt ----------------------------------- #
    recent = store.get_recent_idea_titles(tenant.id, n=history_n)
    plan = claude.expand_to_image_prompt(
        tenant.system_prompt,
        recent_idea_titles=recent,
        today=date.today(),
    )
    idea_title = plan["idea_title"]
    detailed_prompt = plan["detailed_prompt"]

    # ---- Gemini: raw image ------------------------------------------------ #
    raw_bytes = gemini.generate_image(detailed_prompt)

    # ---- Brand framing ---------------------------------------------------- #
    logo_bytes = assets.get_logo_bytes(tenant.phone, tenant.logo_path)
    branded = add_branding(raw_bytes, tenant.theme, tenant.brand, logo_bytes)
    buf = io.BytesIO()
    branded.save(buf, "PNG")
    final_bytes = buf.getvalue()

    # ---- Persist (Storage + local mirror + DB) ---------------------------- #
    basename = _basename(idea_title)
    raw_storage, final_storage = assets.upload_poster_pair(
        tenant.phone, basename, raw=raw_bytes, final=final_bytes
    )
    raw_local, final_local = assets.save_poster_local(
        tenant.phone, basename, raw=raw_bytes, final=final_bytes
    )
    store.save_poster(
        tenant.id,
        idea_title=idea_title,
        detailed_prompt=detailed_prompt,
        image_path=final_storage,
        raw_path=raw_storage,
    )
    tenant = store.increment_quota(tenant.id)

    return GenerationResult(
        tenant_id=str(tenant.id),
        phone=tenant.phone,
        idea_title=idea_title,
        detailed_prompt=detailed_prompt,
        final_local_path=final_local,
        raw_local_path=raw_local,
        final_storage_path=final_storage,
        raw_storage_path=raw_storage,
        quota_used=tenant.quota_used,
        quota_remaining=tenant.quota_remaining,
    )
