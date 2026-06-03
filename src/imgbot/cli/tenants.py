"""`imgbot tenants ...` — inspector + small admin ops on the tenant table."""

from __future__ import annotations

from typing import Optional

import typer

from imgbot.tenants.store import TenantStore


tenants_app = typer.Typer(help="Inspect and adjust tenants.")


@tenants_app.command("list")
def list_tenants() -> None:
    """List every tenant with their quota state."""
    rows = TenantStore().list_tenants()
    if not rows:
        typer.echo("(no tenants yet)")
        return
    for t in rows:
        typer.echo(
            f"{t.phone:<16}  {t.business.name:<30}  "
            f"quota {t.quota_used}/{t.plan_quota}  "
            f"id={t.id}"
        )


@tenants_app.command("info")
def info(phone: str = typer.Argument(..., help="Tenant phone (E.164 or raw).")) -> None:
    """Show one tenant in detail + recent posters."""
    store = TenantStore()
    t = store.get_by_phone(phone)
    if t is None:
        typer.echo(f"no tenant for {phone}", err=True)
        raise typer.Exit(1)

    typer.echo(f"id           : {t.id}")
    typer.echo(f"phone        : {t.phone}")
    typer.echo(f"business     : {t.business.name} — {t.business.type}")
    if t.business.location:
        typer.echo(f"location     : {t.business.location}")
    typer.echo(f"language     : {t.theme.language}")
    typer.echo(f"plan quota   : {t.plan_quota}")
    typer.echo(f"quota used   : {t.quota_used}  (remaining {t.quota_remaining})")
    typer.echo(f"created at   : {t.created_at}")
    typer.echo(f"logo path    : {t.logo_path}")
    typer.echo(f"samples      : {len(t.samples)}")
    typer.echo(f"system prompt: {len(t.system_prompt)} chars")

    recent = store.list_recent_posters(t.id, n=10)
    typer.echo(f"\nrecent posters ({len(recent)}):")
    for p in recent:
        typer.echo(f"  {p.created_at:%Y-%m-%d %H:%M}  [{p.status}]  {p.idea_title}")


@tenants_app.command("update-brand")
def update_brand(
    phone: str = typer.Argument(..., help="Tenant phone (E.164 or raw)."),
    dept_name: Optional[str] = typer.Option(
        None, "--dept-name",
        help="Centred header text. Pass '' to clear (logos-only header band).",
    ),
    social_handle: Optional[str] = typer.Option(
        None, "--social-handle",
        help="Footer-left handle (next to social glyphs). Pass '' to clear.",
    ),
    footer_phone: Optional[str] = typer.Option(
        None, "--footer-phone",
        help="Footer right-stack phone line. Pass '' to clear.",
    ),
    footer_email: Optional[str] = typer.Option(
        None, "--footer-email",
        help="Footer right-stack email line. Pass '' to clear.",
    ),
    footer_website: Optional[str] = typer.Option(
        None, "--footer-website",
        help="Footer right-stack website line. Pass '' to clear.",
    ),
) -> None:
    """Patch a tenant's COMPOSITED brand strings — header text + footer lines.

    No re-onboarding required — these strings drive the Python compositor only,
    not the AI image content. Run with no flags to view the current values.
    """
    store = TenantStore()
    tenant = store.get_by_phone(phone)
    if tenant is None:
        typer.echo(f"no tenant for {phone}", err=True)
        raise typer.Exit(1)

    # Omitted flag (None) → leave field alone. Empty string → null it out.
    raw = {
        "dept_name":      dept_name,
        "social_handle":  social_handle,
        "footer_phone":   footer_phone,
        "footer_email":   footer_email,
        "footer_website": footer_website,
    }
    changes = {k: (v if v != "" else None) for k, v in raw.items() if v is not None}

    if not changes:
        typer.echo(f"current brand strings for {tenant.phone}:")
        typer.echo(f"  dept_name      : {tenant.brand.dept_name!r}")
        typer.echo(f"  social_handle  : {tenant.brand.social_handle!r}")
        typer.echo(f"  footer_phone   : {tenant.brand.footer_phone!r}")
        typer.echo(f"  footer_email   : {tenant.brand.footer_email!r}")
        typer.echo(f"  footer_website : {tenant.brand.footer_website!r}")
        typer.echo("\npass --dept-name 'X' to set, --dept-name '' to clear (same for the others).")
        return

    updated = store.update_brand(tenant.id, changes)
    typer.echo(f"✓ patched {len(changes)} field(s) for {updated.phone}")
    for k, v in changes.items():
        typer.echo(f"  {k:<15} → {v!r}")


@tenants_app.command("set-quota")
def set_quota(
    phone: str = typer.Argument(..., help="Tenant phone."),
    plan_quota: Optional[int] = typer.Option(None, "--plan-quota"),
    quota_used: Optional[int] = typer.Option(None, "--quota-used"),
) -> None:
    """Adjust a tenant's monthly cap or current usage counter."""
    if plan_quota is None and quota_used is None:
        typer.echo("nothing to set; pass --plan-quota and/or --quota-used", err=True)
        raise typer.Exit(1)
    store = TenantStore()
    t = store.get_by_phone(phone)
    if t is None:
        typer.echo(f"no tenant for {phone}", err=True)
        raise typer.Exit(1)
    updated = store.set_quota(t.id, plan_quota=plan_quota, quota_used=quota_used)
    typer.echo(f"✓ {updated.phone} → {updated.quota_used}/{updated.plan_quota}")
