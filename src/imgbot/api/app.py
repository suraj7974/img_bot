"""FastAPI app exposing the web onboarding form.

Two endpoints + a static SPA-ish form page:

  GET  /                serves the HTML onboarding form
  POST /api/onboard     accepts multipart form data, runs the orchestrator,
                        returns the new tenant id + a preview of the generated
                        per-tenant system prompt
  GET  /api/tenants/{phone}   look-up endpoint (operator sanity check)

No auth — run on localhost or behind a private URL (e.g. an ngrok tunnel).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import ValidationError

from imgbot.onboarding.orchestrator import onboard_from_input
from imgbot.tenants.schema import (
    BrandIdentity,
    BusinessInfo,
    TenantMetaInput,
    Theme,
)
from imgbot.tenants.store import TenantStore


STATIC_DIR = Path(__file__).resolve().parent / "static"

app = FastAPI(title="imgbot — onboarding")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# --------------------------------------------------------------------------- #
# Pages
# --------------------------------------------------------------------------- #
@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


# --------------------------------------------------------------------------- #
# API
# --------------------------------------------------------------------------- #
@app.post("/api/onboard")
async def api_onboard(
    business: str = Form(..., description="JSON-encoded BusinessInfo"),
    brand: str = Form(..., description="JSON-encoded BrandIdentity"),
    theme: str = Form("{}", description="JSON-encoded Theme (partial OK)"),
    phone: str = Form(...),
    plan_quota: int = Form(10),
    notes: Optional[str] = Form(None),
    inspiration_ideas: Optional[str] = Form(None),
    logo: UploadFile = File(...),
    samples: Optional[list[UploadFile]] = File(None),
) -> JSONResponse:
    """Run the full onboarding pipeline. Returns the new tenant id + preview."""

    # Parse + validate the JSON blobs the form posts. Pydantic surfaces clean
    # 422-style errors back to the form.
    try:
        meta = TenantMetaInput(
            phone=phone,
            business=BusinessInfo.model_validate(json.loads(business)),
            brand=BrandIdentity.model_validate(json.loads(brand)),
            theme=Theme.model_validate({**Theme().model_dump(), **json.loads(theme or "{}")}),
            plan_quota=plan_quota,
            notes=notes,
            inspiration_ideas=inspiration_ideas,
        )
    except (ValidationError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid input: {exc}")

    logo_bytes = await logo.read()
    if not logo_bytes:
        raise HTTPException(status_code=400, detail="logo file is empty")

    sample_bytes: list[bytes] = []
    for s in samples or []:
        data = await s.read()
        if data:
            sample_bytes.append(data)

    try:
        result = onboard_from_input(meta, logo_bytes=logo_bytes, sample_bytes=sample_bytes)
    except RuntimeError as exc:
        # Already-onboarded conflict, etc.
        raise HTTPException(status_code=409, detail=str(exc))

    t = result.tenant
    return JSONResponse({
        "tenant_id": str(t.id),
        "phone": t.phone,
        "business_name": t.business.name,
        "plan_quota": t.plan_quota,
        "logo_path": result.logo_path,
        "sample_count": len(result.sample_paths),
        "system_prompt_chars": len(result.system_prompt),
        "system_prompt_preview": result.system_prompt[:600],
    })


@app.get("/api/tenants/{phone:path}")
def api_get_tenant(phone: str) -> JSONResponse:
    tenant = TenantStore().get_by_phone(phone)
    if tenant is None:
        raise HTTPException(status_code=404, detail="not onboarded")
    return JSONResponse({
        "id": str(tenant.id),
        "phone": tenant.phone,
        "business_name": tenant.business.name,
        "business_type": tenant.business.type,
        "plan_quota": tenant.plan_quota,
        "quota_used": tenant.quota_used,
        "quota_remaining": tenant.quota_remaining,
        "system_prompt_chars": len(tenant.system_prompt),
    })
