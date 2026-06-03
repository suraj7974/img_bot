"""Supabase-backed tenant + poster store.

Wraps the service-role Supabase client behind a small typed surface used by
onboarding, runtime, and CLI inspection. Pydantic models in `schema.py`
validate every row on the way out — if Supabase returns a dict that doesn't
fit `Tenant`, you get a clean validation error here, not deep in the pipeline.
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Optional
from uuid import UUID

from supabase import Client, create_client

from imgbot import config
from imgbot.tenants.schema import (
    PosterRecord,
    Tenant,
    TenantMetaInput,
    normalize_phone,
)


@lru_cache(maxsize=1)
def _client() -> Client:
    """One process-wide service-role client."""
    config.load_env()
    return create_client(config.supabase_url(), config.supabase_service_key())


class TenantStore:
    """Tenants + posters CRUD on Supabase (all tables under `config.SUPABASE_SCHEMA`)."""

    def __init__(self, client: Optional[Client] = None):
        self._db = client or _client()

    def _t(self, name: str):
        """Schema-scoped table builder — every call goes through this so the
        `img_bot` schema prefix lives in exactly one place."""
        return self._db.schema(config.SUPABASE_SCHEMA).table(name)

    # ---- tenants ---------------------------------------------------------- #
    def get_by_phone(self, phone: str) -> Optional[Tenant]:
        phone = normalize_phone(phone)
        rows = (
            self._t("tenants")
            .select("*")
            .eq("phone", phone)
            .limit(1)
            .execute()
            .data
        )
        return Tenant.model_validate(rows[0]) if rows else None

    def get_by_id(self, tenant_id: UUID | str) -> Optional[Tenant]:
        rows = (
            self._t("tenants")
            .select("*")
            .eq("id", str(tenant_id))
            .limit(1)
            .execute()
            .data
        )
        return Tenant.model_validate(rows[0]) if rows else None

    def list_tenants(self) -> list[Tenant]:
        rows = (
            self._t("tenants")
            .select("*")
            .order("created_at", desc=False)
            .execute()
            .data
        )
        return [Tenant.model_validate(r) for r in rows]

    def create(
        self,
        meta: TenantMetaInput,
        *,
        system_prompt: str,
        logo_path: str,
        sample_paths: list[str],
    ) -> Tenant:
        payload = {
            "phone": meta.phone,
            "business": meta.business.model_dump(),
            "brand": meta.brand.model_dump(),
            "theme": meta.theme.model_dump(),
            "logo_path": logo_path,
            "samples": sample_paths,
            "system_prompt": system_prompt,
            "plan_quota": meta.plan_quota,
            "quota_used": 0,
            "quota_period_start": date.today().isoformat(),
            "notes": meta.notes,
        }
        row = self._t("tenants").insert(payload).execute().data[0]
        return Tenant.model_validate(row)

    def increment_quota(self, tenant_id: UUID | str) -> Tenant:
        """Bump `quota_used` by 1. Re-fetches the row so the caller sees the
        post-increment state. Concurrency is single-writer per tenant (one
        WhatsApp DM at a time), so an RMW here is safe enough for v1."""
        current = self.get_by_id(tenant_id)
        if current is None:
            raise LookupError(f"tenant not found: {tenant_id}")
        new_used = current.quota_used + 1
        row = (
            self._t("tenants")
            .update({"quota_used": new_used})
            .eq("id", str(tenant_id))
            .execute()
            .data[0]
        )
        return Tenant.model_validate(row)

    def set_quota(self, tenant_id: UUID | str, *, plan_quota: Optional[int] = None,
                  quota_used: Optional[int] = None) -> Tenant:
        update: dict = {}
        if plan_quota is not None:
            update["plan_quota"] = plan_quota
        if quota_used is not None:
            update["quota_used"] = quota_used
        if not update:
            raise ValueError("set_quota called with nothing to set")
        row = (
            self._t("tenants")
            .update(update)
            .eq("id", str(tenant_id))
            .execute()
            .data[0]
        )
        return Tenant.model_validate(row)

    # ---- posters ---------------------------------------------------------- #
    def get_recent_idea_titles(self, tenant_id: UUID | str, n: int = 8) -> list[str]:
        rows = (
            self._t("posters")
            .select("idea_title")
            .eq("tenant_id", str(tenant_id))
            .eq("status", "done")
            .order("created_at", desc=True)
            .limit(n)
            .execute()
            .data
        )
        return [r["idea_title"] for r in rows]

    def list_recent_posters(self, tenant_id: UUID | str, n: int = 10) -> list[PosterRecord]:
        rows = (
            self._t("posters")
            .select("*")
            .eq("tenant_id", str(tenant_id))
            .order("created_at", desc=True)
            .limit(n)
            .execute()
            .data
        )
        return [PosterRecord.model_validate(r) for r in rows]

    def save_poster(
        self,
        tenant_id: UUID | str,
        *,
        idea_title: str,
        detailed_prompt: str,
        image_path: Optional[str] = None,
        raw_path: Optional[str] = None,
        status: str = "done",
        error: Optional[str] = None,
    ) -> PosterRecord:
        row = (
            self._t("posters")
            .insert(
                {
                    "tenant_id": str(tenant_id),
                    "idea_title": idea_title,
                    "detailed_prompt": detailed_prompt,
                    "image_path": image_path,
                    "raw_path": raw_path,
                    "status": status,
                    "error": error,
                }
            )
            .execute()
            .data[0]
        )
        return PosterRecord.model_validate(row)
