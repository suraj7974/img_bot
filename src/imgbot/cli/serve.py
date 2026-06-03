"""`imgbot serve` — run the FastAPI onboarding app under uvicorn."""

from __future__ import annotations

import typer
import uvicorn


def serve_cmd(
    host: str = typer.Option("127.0.0.1", "--host", help="Bind address. Use 0.0.0.0 for LAN / ngrok."),
    port: int = typer.Option(8000, "--port"),
    reload: bool = typer.Option(False, "--reload", help="Auto-reload on file changes (dev)."),
) -> None:
    """Start the onboarding web app on http://<host>:<port>."""
    typer.echo(f"→ imgbot onboarding app at http://{host}:{port}")
    uvicorn.run("imgbot.api.app:app", host=host, port=port, reload=reload)
