"""imgbot CLI entry point.

Subcommands:
  imgbot serve      — onboarding web app
  imgbot generate   — produce one poster for a tenant (called by the WA bot)
  imgbot tenants    — inspector + small admin ops
"""

from __future__ import annotations

import typer

from imgbot.cli.generate import generate_cmd
from imgbot.cli.serve import serve_cmd
from imgbot.cli.tenants import tenants_app


app = typer.Typer(help="imgbot — multi-tenant AI poster pipeline.", no_args_is_help=True)

app.command("serve")(serve_cmd)
app.command("generate")(generate_cmd)
app.add_typer(tenants_app, name="tenants")


if __name__ == "__main__":
    app()
