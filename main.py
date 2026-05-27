"""Poster pipeline — query in, several branded posters out.

Steps:
  1. Expand the query into N design-variant prompts  (GeminiClient.generate_prompts)
  2. Generate a poster image from each prompt          (GeminiClient.generate_image)
  3. Frame each with the header + footer band          (compositor.add_branding)

All variants share the same data; only the design differs.

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

    print("→ [1/3] Building design-variant prompts with", config.TEXT_MODEL, "...")
    variants = client.generate_prompts(user_query)
    print(f"    got {len(variants)} variant prompt(s)")

    finals = []
    for i, prompt in enumerate(variants, start=1):
        tag = f"v{i}"
        prompt_path = base.with_suffix(f".{tag}.prompt.txt")
        prompt_path.write_text(prompt, encoding="utf-8")

        print(f"→ [2/3] Variant {i}/{len(variants)}: generating image with",
              config.IMAGE_MODEL, "...")
        try:
            raw = client.generate_image(prompt)
        except Exception as exc:  # one bad variant shouldn't sink the rest
            print(f"    ✗ variant {i} failed: {exc}")
            continue
        raw_path = base.with_suffix(f".{tag}.raw.png")
        raw_path.write_bytes(raw)

        print(f"→ [3/3] Variant {i}/{len(variants)}: adding header + footer ...")
        final = compositor.add_branding(raw)
        final_path = base.with_suffix(f".{tag}.final.png")
        final.save(final_path)
        finals.append(final_path)
        print(f"    ✓ {final_path.name}")

    if not finals:
        raise RuntimeError("No posters were produced (all variants failed).")
    print(f"\n✓ Done. {len(finals)} poster(s):")
    for p in finals:
        print(f"    {p}")


if __name__ == "__main__":
    query = " ".join(sys.argv[1:]).strip() or input("Enter your query: ").strip()
    if not query:
        sys.exit("No query provided.")
    run(query)
