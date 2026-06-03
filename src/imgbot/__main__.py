"""Module entry point so `python -m imgbot ...` works (matches what the
WhatsApp bot spawns and what the `imgbot` console script invokes)."""

from imgbot.cli.__main__ import app


if __name__ == "__main__":
    app()
