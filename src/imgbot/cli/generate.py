"""`imgbot generate --phone <e164>` — produce one poster for a tenant.

stdout contract (consumed by the WhatsApp bot):
  * One line per step prefixed `→ ` for human eyes
  * A legacy line `✓ Final poster -> <abs path>` for the bot's regex
  * A final JSON line on a clean line by itself:
      {"image_path": "...", "raw_path": "...", "idea_title": "...", "quota_remaining": N}

On failure: exit non-zero and print a JSON error line.
"""

from __future__ import annotations

import json
import sys

import typer

from imgbot.pipeline.generate import (
    QuotaExceeded,
    TenantNotFound,
    run_for_phone,
)


def generate_cmd(
    phone: str = typer.Option(..., "--phone", help="Tenant's WhatsApp phone (E.164 or raw)."),
) -> None:
    """Run the full pipeline for one phone number."""
    try:
        result = run_for_phone(phone)
    except TenantNotFound as exc:
        sys.stderr.write(json.dumps({"error": "not_onboarded", "message": str(exc)}) + "\n")
        raise typer.Exit(2)
    except QuotaExceeded as exc:
        sys.stderr.write(json.dumps({"error": "quota_exceeded", "message": str(exc)}) + "\n")
        raise typer.Exit(3)

    typer.echo(f"→ idea  : {result.idea_title}")
    typer.echo(f"→ quota : {result.quota_used}  remaining {result.quota_remaining}")
    # Legacy line kept for the bot's existing stdout-scrape regex.
    typer.echo(f"✓ Final poster -> {result.final_local_path}")
    # Structured payload the bot can parse to get the caption.
    typer.echo(json.dumps({
        "image_path": str(result.final_local_path),
        "raw_path": str(result.raw_local_path),
        "idea_title": result.idea_title,
        "quota_remaining": result.quota_remaining,
    }))
