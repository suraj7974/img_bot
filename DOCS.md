# imgbot — system reference

A multi-tenant AI poster pipeline. Each paying customer (a small or mid-size Indian business) is onboarded once via a web dashboard; from then on, when they DM the WhatsApp bot with `new poster`, an AI pipeline produces one branded, on-brand poster and ships it back — drawing on the tenant's profile, a rolling history of what they've already produced, today's date, and an operator-curated trends pool.

For setup / testing steps see [USAGE.md](./USAGE.md). This doc is the architecture + data + pipeline reference.

---

## At a glance

```
                    ┌─────────────────────────────────────────────┐
                    │            OPERATOR (you)                   │
                    │                                             │
       Onboarding ──┤  http://localhost:8000/        (Dashboard)  │
                    └────────────────┬────────────────────────────┘
                                     │
                                     │ HTTP (FastAPI)
                                     ▼
       ┌───────────────────────────────────────────────────────────┐
       │            Python package `imgbot` (`src/imgbot/`)         │
       │                                                            │
       │  api/   FastAPI app + HTML dashboard                       │
       │  cli/   typer CLI:  serve / generate / tenants             │
       │  ai/    GeminiImageClient    + ClaudeClient                │
       │  onboarding/   meta-prompts + orchestrator                 │
       │  pipeline/     runtime prompt + brand compositor +         │
       │                end-to-end generate.run_for_phone()         │
       │  tenants/      Pydantic schema, Supabase store, assets     │
       └────────┬────────────────────┬─────────────────┬────────────┘
                │                    │                 │
        Anthropic API           Gemini API        Supabase
       (Opus / Sonnet)        (3 Flash Image)   ┌───────────────────┐
                                                │ Postgres schema   │
                                                │  img_bot.tenants  │
                                                │  img_bot.posters  │
                                                ├───────────────────┤
                                                │ Storage buckets   │
                                                │  tenant-logos     │
                                                │  tenant-samples   │
                                                │  tenant-posters   │
                                                └───────────────────┘
                                     ▲
                                     │
                                     │ subprocess (python -m imgbot generate --phone …)
                                     │
                    ┌────────────────┴────────────────────────────┐
                    │  whatsapp-bot/bot.js  (whatsapp-web.js)     │
                    │  Listens for DMs starting "new poster",     │
                    │  spawns the CLI, ships the final PNG back.  │
                    └─────────────────────────────────────────────┘
```

---

## Layout

```
img_bot/
├── pyproject.toml            # package metadata + deps + `imgbot` console script
├── .env(.example)            # GEMINI_API_KEY, ANTHROPIC_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_KEY
├── DOCS.md                   # ← you are here
├── USAGE.md                  # step-by-step dev / test guide
├── src/imgbot/
│   ├── config.py             # model IDs, paths, Supabase schema name, key loaders
│   ├── ai/
│   │   ├── claude.py         # ClaudeClient: build_system_prompt + expand_to_image_prompt
│   │   └── gemini.py         # GeminiImageClient: render PNG bytes
│   ├── api/
│   │   ├── app.py            # FastAPI routes (onboard, trends, tenant lookup)
│   │   └── static/           # index.html, trends.html  (Tailwind CDN, no build step)
│   ├── cli/
│   │   ├── __main__.py       # typer app entrypoint
│   │   ├── serve.py          # `imgbot serve` — runs uvicorn against api.app
│   │   ├── generate.py       # `imgbot generate --phone <e164>` — one-shot
│   │   └── tenants.py        # `imgbot tenants list | info | set-quota`
│   ├── onboarding/
│   │   ├── meta_prompts.py   # the instructions + worked examples Opus reads
│   │   └── orchestrator.py   # onboard_from_input(meta, logo_bytes, sample_bytes)
│   ├── pipeline/
│   │   ├── brand.py          # header + footer compositor (Pillow + RAQM)
│   │   ├── generate.py       # phone -> branded poster (Supabase + cache + quota)
│   │   └── prompts/runtime.py # the user-turn template for the runtime Claude call
│   └── tenants/
│       ├── schema.py         # Pydantic: BusinessInfo, BrandIdentity, Theme, Tenant, …
│       ├── store.py          # TenantStore (Supabase tables under `img_bot` schema)
│       └── assets.py         # AssetStore (Supabase Storage uploads + local mirror)
├── supabase/schema.sql       # idempotent — schema + grants + tables + buckets
├── whatsapp-bot/             # Node.js whatsapp-web.js bot
│   └── bot.js
└── data/                     # local mirror (gitignored): logos, generated posters
```

---

## Data model

### Postgres (`img_bot` schema, NOT `public`)

#### `img_bot.tenants` — one row per paying customer

| Column                | Type        | Notes |
|-----------------------|-------------|-------|
| `id`                  | uuid PK     | server-generated |
| `phone`               | text UNIQUE | E.164 (`+91…`); WhatsApp DM sender phone |
| `business`            | jsonb       | `BusinessInfo` — name, type, location, tagline, language, audience, tone, notes |
| `brand`               | jsonb       | `BrandIdentity` — dept_name (header text), social_handle, footer_phone/email/website |
| `theme`               | jsonb       | `Theme` — band colours (hex), height ratios, header_logo_height_ratio, language |
| `logo_path`           | text        | Supabase Storage path inside `tenant-logos` |
| `samples`             | jsonb       | array of Storage paths under `tenant-samples` |
| `system_prompt`       | text        | the long per-tenant prompt Opus 4.8 produced during onboarding |
| `plan_quota`          | int         | monthly cap (default 10) |
| `quota_used`          | int         | bumps once per successful generation |
| `quota_period_start`  | date        | reserved for monthly resets (not auto-rolled yet) |
| `notes`               | text        | operator notes |
| `created_at`          | timestamptz | server-set |
| `updated_at`          | timestamptz | bumped by trigger `img_bot.touch_updated_at()` |

#### `img_bot.posters` — one row per generated poster (history + audit trail)

| Column            | Type     | Notes |
|-------------------|----------|-------|
| `id`              | uuid PK  | |
| `tenant_id`       | uuid FK  | cascades on tenant delete |
| `idea_title`      | text     | ≤8 words; doubles as WhatsApp caption AND seeds future "don't repeat" history |
| `detailed_prompt` | text     | the full image-gen prompt Claude emitted — sent to Gemini |
| `image_path`      | text     | Storage path of the branded `.final.png` |
| `raw_path`        | text     | Storage path of the un-branded `.raw.png` |
| `status`          | text     | `done` \| `failed` |
| `error`           | text     | populated when status=failed |
| `created_at`      | timestamptz | |

Index: `posters_tenant_created_idx (tenant_id, created_at desc)` — supports the "give me the last N idea titles" lookup at runtime.

### Storage buckets

| Bucket            | Public? | What's in it |
|-------------------|---------|--------------|
| `tenant-logos`    | yes     | one logo per tenant, paths like `<phone>/logo.png` |
| `tenant-samples`  | no      | reference posters shown to Opus at onboarding |
| `tenant-posters`  | no      | every generated poster, paths like `<phone>/<ts>_<slug>.final.png` (+ `.raw.png`) |

### Local cache mirror — `data/tenants/<phone>/`

Logos are downloaded once from Storage and cached locally so the runtime pipeline doesn't pay a network round-trip per generation. Generated posters land here too so the WhatsApp bot can `MessageMedia.fromFilePath()` without a re-download. `data/` is gitignored.

---

## AI pipeline

There are **three** AI calls in this system. Two are Claude, one is Gemini.

### Step 0 — Onboarding (Sonnet 4.6 + vision, forced tool output)  · `ClaudeClient.build_system_prompt`

**Fires:** once per tenant during onboarding (`POST /api/onboard`).
**Inputs:**
- structured tenant metadata as JSON
- the operator's free-text "inspiration / ideas" block (optional)
- 0+ sample posters the customer likes, attached as base64 image blocks (vision)
- a meta-prompt with **two worked examples** (the prior Baster premium-events prompt + a condensed police infographic prompt) baked into `onboarding/meta_prompts.py`

**Trends.** The TRENDS / FRESHNESS / CALENDAR section inside the generated system prompt is seeded from Sonnet's training knowledge (cutoff Jan 2026 covers the full 2026 Indian festival calendar — Diwali, Holi, Onam, Eid, Karva Chauth, regional events like Bastar Dussehra, etc.). Earlier versions used the `web_search_20260209` server tool here, but that combined with adaptive thinking + a `pause_turn` retry loop could burn $1+ and 15 minutes per onboarding for almost no incremental quality on SMB poster generation. Trends now come from the model directly.

**Forced tool output.** The call defines an `emit_system_prompt` tool and forces `tool_choice` to it. The model's `tool_use.input["system_prompt"]` is the saved value — no preamble or narration can leak in.

**Settings:** `thinking: {"type": "disabled"}`, `effort: "medium"`, `max_tokens: 8000`. One bounded call, ~10-20 s, ~$0.05-0.10.

**Output:** the per-tenant system prompt as a clean string. Typically 10K–20K chars. Persisted to `tenants.system_prompt` and never regenerated unless the operator re-onboards.

### Step 1 — Runtime expansion (Sonnet 4.6, forced tool-use) · `ClaudeClient.expand_to_image_prompt`

**Fires:** every time a tenant requests a poster.
**Inputs:**
- the tenant's `system_prompt` from step 0 — sent as a cached system block (`cache_control: ephemeral`). This carries all brand voice, structural rules, trend / freshness contract, and business-relevance rules baked in at onboarding.
- a small user message assembled fresh each call:
  - today's date
  - the last 12 `idea_title`s this tenant produced (the "don't repeat" pool)
- a forced `tool_choice = emit_poster_plan` to guarantee the output parses as `{ idea_title, detailed_prompt }`

**Output:** `{ idea_title: str (≤8 words), detailed_prompt: str (dense image-gen prompt) }`

**Notes:**
- Thinking is OFF here — Anthropic 400s if adaptive thinking is combined with forced `tool_choice`. We use `effort: high` to compensate (more careful inline reasoning).
- The cached system prompt is the dominant input — after the first call within ~5 minutes, subsequent calls for the same tenant pay ~0.1× for that block (Anthropic prompt cache reads).
- `max_tokens: 8192` gives Claude room to write a dense detailed prompt without truncation.

### Step 2 — Render (Gemini 3 Flash Image) · `GeminiImageClient.generate_image`

**Fires:** once per generation, after step 1.
**Input:** the `detailed_prompt` string from step 1.
**Output:** raw PNG bytes (the unbranded poster).

### Step 3 — Branding (Python, pure Pillow) · `pipeline.brand.add_branding`

**Fires:** once per generation, after step 2.
**What:** prepends a coloured header band (logo on left + right, business name centred) above the rendered image, appends a coloured footer band (social glyphs + handle on left, contact lines stacked on right) below it. Header and footer share a palette pulled from `Theme`.

Pillow renders Hindi text via the RAQM layout engine for correct Devanagari conjuncts; the system falls back to the Latin font for English-only tenants based on `Theme.language`.

---

## Prompt caching, in one paragraph

The per-tenant `system_prompt` is identical on every runtime call for that tenant. We send it as a single `cache_control: ephemeral` system block. Anthropic caches it for ~5 minutes after the first read; subsequent calls within the window read it at ~0.1× input price. The volatile parts (history, date, trends) live in the user message AFTER the cached block, so they don't invalidate the cache. Result: a tenant burst-generating 5 posters in 10 minutes pays full input price for the system prompt **once**, not five times.

---

## Trends, freshness, diversity

**All trend / freshness rules live inside the per-tenant system prompt**, baked in once at onboarding. The runtime user message carries only two rolling pieces:

1. **`today`** — actual date.
2. **`recent_idea_titles`** — the last 12 successful `idea_title`s for this tenant.

The system prompt is responsible for everything else — festival calendar, seasonal beats, business-relevance rules, the trend / evergreen ratio. Runtime stays minimal so the bytes after the cached system block are as small as possible (cheap, and trends are an onboarding concern).

**Phase 2 — richer trend awareness** is parked. Candidates when we revisit:
- Daily cron + shared `trend_feeds(industry, trends, fetched_at)` so acute trends amortise across all tenants in an industry.
- `TREND_WINDOW_DAYS` tenant-level knob.
- Operator-curated trend pool per tenant (an explicit "weekly nudge" field).

**Refresh strategy today:** the trend awareness inside the system prompt is frozen at onboarding time. Re-onboard the tenant every few months (drop the row, resubmit the form) to refresh it from Claude's then-current training knowledge.

---

## Quota model

`tenants.plan_quota` is the monthly cap. `tenants.quota_used` increments by 1 after each successful `pipeline.generate.run_for_phone()`. Before a generation runs, the pipeline checks `quota_remaining > 0`; if not, it raises `QuotaExceeded` and prints a clean stderr-JSON for the bot to translate into a user-facing message.

**Reset is manual today.** `quota_period_start` exists but there's no cron rolling it. To reset a tenant mid-month: `imgbot tenants set-quota <phone> --quota-used 0` (or set it back via Supabase SQL).

---

## CLI

```
imgbot serve     [--host 127.0.0.1] [--port 8000] [--reload]
imgbot generate  --phone <e164>
imgbot tenants list
imgbot tenants info <phone>
imgbot tenants set-quota <phone> [--plan-quota N] [--quota-used N]
```

There is **no** `imgbot onboard` — onboarding is web-only (the YAML path was removed once the dashboard shipped).

---

## WhatsApp integration contract

The bot (`whatsapp-bot/bot.js`) is a thin shell around the Python CLI:

- Subscribes to incoming chat messages, filters to DMs only (`if (chat.isGroup) return`).
- A message body starting with `new poster` (case-insensitive) is the trigger.
- Resolves the sender's WhatsApp ID (`917974387273@c.us`) to E.164 (`+917974387273`).
- Spawns `python -m imgbot generate --phone <e164>` from the repo root using `.venv/bin/python` (overridable via `PYTHON_BIN`).
- Parses the last JSON line of stdout for `{ image_path, idea_title, quota_remaining }` and the legacy `✓ Final poster -> <path>` line as a fallback.
- Sends the file via `MessageMedia.fromFilePath()` with `idea_title` as the caption.
- Cleans up the local `.raw.png` and `.final.png` after a successful send.
- Translates structured stderr-JSON errors (`not_onboarded`, `quota_exceeded`) into user-friendly replies.

---

## Failure modes & current limitations

- **Concurrency:** Quota bump is read-modify-write inside Python (no `... set quota_used = quota_used + 1 returning *`). Fine while one WhatsApp DM at a time per tenant — would race under heavy concurrency. Lift later with an RPC.
- **No automatic quota reset.** `quota_period_start` is informational; you reset by hand.
- **No retries.** Gemini refusals / 5xx surface to the user as an error message. Easy to add a retry-with-jitter wrapper.
- **No multi-variant.** Old pipeline produced N design variants per query; new one produces one focused poster per call. Trivial to resurrect by looping the Sonnet+Gemini steps.
- **No auth on the dashboard.** Run on localhost or behind a private URL (ngrok). Add a simple admin password before exposing publicly.
- **Trend awareness drifts over time.** The TRENDS / CALENDAR section is frozen at onboarding. Re-onboard every few months to refresh it. A future v2 could move web search into the runtime path (paid per call) or add a periodic re-research job.
- **No periodic system-prompt refresh.** If a tenant's brand evolves or trends drift, you re-onboard.

---

## Roadmap (rough)

- Atomic quota RPC + monthly reset cron.
- Customer self-serve onboarding (Supabase Auth + RLS policies on `img_bot.tenants`).
- Periodic trend refresh — either a cron that re-runs the Opus call against existing tenants, or move web search into the Sonnet runtime path.
- Multi-variant generation (loop N times in `pipeline.generate.run_for_phone`).
- Billing wiring (Stripe webhooks → `plan_quota` increase).
- An ops dashboard page showing recent posters per tenant + their generated prompts.
