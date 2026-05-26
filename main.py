"""Poster pipeline — query in, branded poster out.

Steps:
  1. Expand the user's query into a dense prompt   (GeminiClient.generate_prompt)
  2. Generate the poster image from that prompt     (GeminiClient.generate_image)
  3. Overlay the police logo + footer band          (compositor.add_branding)

Usage:
    python main.py "your topic / facts here"
    python main.py                # then type the query when prompted

Requires GEMINI_API_KEY in the environment or a .env file.
"""

import sys
from datetime import datetime

import config
import compositor
from ai import GeminiClient


def _slug(text: str, n: int = 40) -> str:
    keep = "".join(c if c.isalnum() or c in " -_" else " " for c in text)
    return "_".join(keep.split())[:n] or "poster"


def run(user_query: str) -> None:
    client = GeminiClient()
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = config.OUTPUT_DIR / f"{stamp}_{_slug(user_query)}"

    print("→ [1/3] Building detailed prompt with", config.TEXT_MODEL, "...")
    detailed = client.generate_prompt(user_query)
    prompt_path = base.with_suffix(".prompt.txt")
    prompt_path.write_text(detailed, encoding="utf-8")
    print(f"    saved prompt -> {prompt_path.name}")

    print("→ [2/3] Generating image with", config.IMAGE_MODEL, "...")
    raw = client.generate_image(detailed)
    raw_path = base.with_suffix(".raw.png")
    raw_path.write_bytes(raw)
    print(f"    saved raw image -> {raw_path.name}")

    print("→ [3/3] Adding logo header + footer band ...")
    final = compositor.add_branding(raw)
    final_path = base.with_suffix(".final.png")
    final.save(final_path)
    print(f"\n✓ Done. Final poster -> {final_path}")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or input("Enter your query: ").strip()
    if not query:
        sys.exit("No query provided.")
    run(query)
