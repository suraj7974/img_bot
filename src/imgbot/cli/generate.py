"""`imgbot generate` — produce one poster for a tenant.

Accepts EITHER `--chat-id <jid>` (what the WhatsApp bot passes) or
`--phone <number>` (handy for manual testing without the bot loop), or BOTH
(bot uses this when it can resolve a phone for an @lid sender — Python then
looks up by phone and binds the chat_id for next time).

stdout contract (consumed by the WhatsApp bot):
  * One line per step prefixed `→ ` for human eyes
  * A legacy line `✓ Final poster -> <abs path>` for the bot's regex
  * A final JSON line on a clean line by itself:
      {"image_path": "...", "raw_path": "...", "idea_title": "...", "quota_remaining": N}

On failure: exit non-zero and print a JSON error line.
"""

from __future__ import annotations

import io
import json
import sys
from datetime import date, datetime
from typing import Optional

import typer

from imgbot.ai.claude import ClaudeClient
from imgbot.ai.gemini import GeminiImageClient
from imgbot.pipeline.brand import add_branding
from imgbot.pipeline.generate import (
    QuotaExceeded,
    TenantNotFound,
    _basename,
    GenerationResult,
)
from imgbot.tenants.assets import AssetStore
from imgbot.tenants.schema import normalize_phone
from imgbot.tenants.store import TenantStore


def _resolve(
    store: TenantStore,
    *,
    chat_id: Optional[str],
    phone: Optional[str],
):
    """Tenant lookup: chat_id fast path → phone fallback → @c.us derived digits."""
    if chat_id:
        hit = store.get_by_chat_id(chat_id)
        if hit is not None:
            return hit, chat_id
    if phone:
        hit = store.get_by_phone(phone)
        if hit is not None:
            return hit, chat_id
    if chat_id and chat_id.endswith("@c.us"):
        digits = chat_id.split("@", 1)[0]
        hit = store.get_by_phone("+" + digits)
        if hit is not None:
            return hit, chat_id
    return None, chat_id


def generate_cmd(
    chat_id: Optional[str] = typer.Option(
        None, "--chat-id",
        help="Tenant's WhatsApp JID (e.g. `917974387273@c.us`, `170424…@lid`).",
    ),
    phone: Optional[str] = typer.Option(
        None, "--phone",
        help="10-digit Indian mobile or +<cc><number>. Used alone (manual test) "
             "or with --chat-id (bot supplies it when resolving an @lid).",
    ),
) -> None:
    """Run the full pipeline for one tenant."""
    if not chat_id and not phone:
        typer.echo("error: provide --chat-id or --phone (or both)", err=True)
        raise typer.Exit(2)

    # Normalise the phone hint (and strip if invalid — never fail the call over a bad hint).
    norm_phone: Optional[str] = None
    if phone:
        try:
            norm_phone = normalize_phone(phone)
        except ValueError:
            pass

    store = TenantStore()
    assets = AssetStore()
    claude = ClaudeClient()
    gemini = GeminiImageClient()

    tenant, sender_chat_id = _resolve(store, chat_id=chat_id, phone=norm_phone)
    if tenant is None:
        ident = chat_id or norm_phone or phone
        sys.stderr.write(json.dumps({
            "error": "not_onboarded",
            "message": f"no onboarded tenant for {ident}",
        }) + "\n")
        raise typer.Exit(2)

    # First-contact chat_id binding — store whatever WhatsApp's giving us now
    # (especially the @lid) so the next run skips the resolve dance entirely.
    if sender_chat_id and tenant.chat_id != sender_chat_id.lower():
        try:
            tenant = store.bind_chat_id(tenant.id, sender_chat_id)
        except Exception:
            pass

    if tenant.quota_remaining <= 0:
        sys.stderr.write(json.dumps({
            "error": "quota_exceeded",
            "message": (
                f"tenant {tenant.phone} is out of quota "
                f"({tenant.quota_used}/{tenant.plan_quota} used)"
            ),
        }) + "\n")
        raise typer.Exit(3)

    # ---- Claude: idea + detailed prompt -------------------------------------
    recent = store.get_recent_idea_titles(tenant.id, n=12)
    plan = claude.expand_to_image_prompt(
        tenant.system_prompt,
        recent_idea_titles=recent,
        today=date.today(),
    )

    # ---- Gemini render ------------------------------------------------------
    raw_bytes = gemini.generate_image(plan["detailed_prompt"])

    # ---- Brand + persist (same flow as pipeline.generate.run_for_chat_id) ---
    logo_bytes = assets.get_logo_bytes(tenant.phone, tenant.logo_path)
    branded = add_branding(raw_bytes, tenant.theme, tenant.brand, logo_bytes)
    buf = io.BytesIO()
    branded.save(buf, "PNG")
    final_bytes = buf.getvalue()

    basename = _basename(plan["idea_title"])
    raw_storage, final_storage = assets.upload_poster_pair(
        tenant.phone, basename, raw=raw_bytes, final=final_bytes
    )
    raw_local, final_local = assets.save_poster_local(
        tenant.phone, basename, raw=raw_bytes, final=final_bytes
    )
    store.save_poster(
        tenant.id,
        idea_title=plan["idea_title"],
        detailed_prompt=plan["detailed_prompt"],
        image_path=final_storage,
        raw_path=raw_storage,
    )
    tenant = store.increment_quota(tenant.id)

    typer.echo(f"→ idea  : {plan['idea_title']}")
    typer.echo(f"→ quota : {tenant.quota_used}  remaining {tenant.quota_remaining}")
    typer.echo(f"✓ Final poster -> {final_local}")
    typer.echo(json.dumps({
        "image_path": str(final_local),
        "raw_path": str(raw_local),
        "idea_title": plan["idea_title"],
        "quota_remaining": tenant.quota_remaining,
    }))
