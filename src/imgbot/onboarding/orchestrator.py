"""Onboarding orchestrator — one tenant per call.

Takes a validated `TenantMetaInput`, the logo bytes, optional sample-poster
bytes, and an optional free-text `inspiration_ideas` block; uploads the
binaries to Supabase Storage, asks Claude (Opus 4.8) to write a tenant-
specific system prompt, and inserts the `tenants` row.

The web onboarding form (`imgbot.api`) is the only caller in production — the
yaml entry point was removed when we moved to a self-serve UX.
"""

from __future__ import annotations

from dataclasses import dataclass

from imgbot.ai.claude import ClaudeClient
from imgbot.tenants.assets import AssetStore
from imgbot.tenants.schema import Tenant, TenantMetaInput
from imgbot.tenants.store import TenantStore


@dataclass
class OnboardResult:
    tenant: Tenant
    logo_path: str
    sample_paths: list[str]
    system_prompt: str


def onboard_from_input(
    meta: TenantMetaInput,
    *,
    logo_bytes: bytes,
    sample_bytes: list[bytes] | None = None,
    replace: bool = False,
    store: TenantStore | None = None,
    assets: AssetStore | None = None,
    claude: ClaudeClient | None = None,
) -> OnboardResult:
    """Run the full onboarding pipeline for one tenant.

    Parameters
    ----------
    meta
        Validated structured metadata (business / brand / theme / phone +
        optional `inspiration_ideas`).
    logo_bytes
        Raw bytes of the tenant's logo PNG/JPEG.
    sample_bytes
        Optional list of reference-poster bytes Claude can look at (vision).
    """
    sample_bytes = sample_bytes or []
    store = store or TenantStore()
    assets = assets or AssetStore()
    claude = claude or ClaudeClient()

    existing = store.get_by_phone(meta.phone)
    if existing is not None and not replace:
        raise RuntimeError(
            f"Tenant already onboarded for phone {meta.phone} (id={existing.id})."
        )

    # ---- upload binaries -------------------------------------------------- #
    logo_path = assets.upload_logo(meta.phone, logo_bytes)
    sample_paths = [
        assets.upload_sample(meta.phone, i, b) for i, b in enumerate(sample_bytes)
    ]

    # ---- build per-tenant system prompt ----------------------------------- #
    # We deliberately strip `business.tagline` and `brand.*` strings (header
    # text, social handle, footer contact lines) before sending to Claude —
    # those are composited-only by the brand pipeline and should NEVER appear
    # inside the AI-rendered image. Withholding them from Claude entirely is
    # the strongest guardrail against leakage; the meta-prompt's "do not
    # render" rule alone wasn't always being followed.
    business_for_claude = meta.business.model_dump()
    business_for_claude.pop("tagline", None)
    meta_for_claude = {
        "business": business_for_claude,
        "theme": meta.theme.model_dump(),
        "plan_quota": meta.plan_quota,
        "notes": meta.notes,
    }
    system_prompt = claude.build_system_prompt(
        meta_for_claude,
        sample_images=sample_bytes,
        inspiration_ideas=meta.inspiration_ideas,
    )

    # ---- persist ---------------------------------------------------------- #
    tenant = store.create(
        meta,
        system_prompt=system_prompt,
        logo_path=logo_path,
        sample_paths=sample_paths,
    )

    return OnboardResult(
        tenant=tenant,
        logo_path=logo_path,
        sample_paths=sample_paths,
        system_prompt=system_prompt,
    )
