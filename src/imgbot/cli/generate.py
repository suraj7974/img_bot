"""`imgbot generate --phone <number>` — produce one poster for a tenant.

The WhatsApp bot resolves the sender's phone (from `message.from` for
phone-based accounts, or via the Contact API for LID-protected accounts)
and passes it here as `--phone`. Tenant lookup is phone-only.

stdout contract (consumed by the WhatsApp bot):
  * One line per step prefixed `→ ` for human eyes
  * A legacy line `✓ Final poster -> <abs path>` for the bot's regex
  * A final JSON line on a clean line by itself:
      {"image_path": "...", "raw_path": "...", "idea_title": "...", "quota_remaining": N}

On failure: exit non-zero and print a JSON error line on stderr.
"""

from __future__ import annotations

import json
import sys

import typer

from imgbot.pipeline.generate import QuotaExceeded, TenantNotFound, run_for_phone
from imgbot.tenants.schema import normalize_phone


def generate_cmd(
    phone: str = typer.Option(
        ..., "--phone",
        help="Tenant phone in E.164 (`+91…`) or bare 10-digit Indian mobile.",
    ),
) -> None:
    """Run the full pipeline for one tenant identified by phone."""
    try:
        norm_phone = normalize_phone(phone)
    except ValueError as exc:
        sys.stderr.write(json.dumps({"error": "bad_phone", "message": str(exc)}) + "\n")
        raise typer.Exit(2)

    try:
        result = run_for_phone(norm_phone)
    except TenantNotFound as exc:
        sys.stderr.write(json.dumps({"error": "not_onboarded", "message": str(exc)}) + "\n")
        raise typer.Exit(2)
    except QuotaExceeded as exc:
        sys.stderr.write(json.dumps({"error": "quota_exceeded", "message": str(exc)}) + "\n")
        raise typer.Exit(3)

    typer.echo(f"→ idea  : {result.idea_title}")
    typer.echo(f"→ quota : {result.quota_used}  remaining {result.quota_remaining}")
    typer.echo(f"✓ Final poster -> {result.final_local_path}")
    typer.echo(json.dumps({
        "image_path": str(result.final_local_path),
        "raw_path": str(result.raw_local_path),
        "idea_title": result.idea_title,
        "quota_remaining": result.quota_remaining,
    }))
