# imgbot — usage & testing guide

Step-by-step setup and end-to-end test path. Follow top-to-bottom on a fresh machine; skim and jump if you've already done parts.

For the architecture / data-model / pipeline reference, see [DOCS.md](./DOCS.md).

---

## 0. Prerequisites

| What                 | Version            | Why |
|----------------------|--------------------|-----|
| Python               | 3.11+              | the package + CLI |
| Node.js              | 18+                | whatsapp-web.js bot |
| A Supabase project   | any plan, free OK  | Postgres + Storage |
| An Anthropic API key | with Claude access | onboarding + runtime prompt brain |
| A Gemini API key     | with image-gen     | actual poster rendering |
| Homebrew (macOS) or `apt` (Linux) | — | for system fonts (Hindi rendering) |

macOS already ships the Devanagari + Arial fonts. Ubuntu / Debian:
```bash
sudo apt install -y fonts-noto fonts-liberation
```

---

## 1. Clone, venv, deps

```bash
git clone <your-fork>.git img_bot
cd img_bot

python3.11 -m venv .venv
.venv/bin/pip install -U pip
.venv/bin/pip install -e .
```

`pip install -e .` installs the package in editable mode plus all deps (anthropic, google-genai, fastapi, uvicorn, supabase, pydantic, typer, pillow, …) and adds the `imgbot` console script to `.venv/bin/`.

Sanity check:
```bash
.venv/bin/imgbot --help
```

You should see `serve`, `generate`, `tenants` as subcommands.

---

## 2. Supabase setup

### 2a. Create the project

In the Supabase dashboard: **New project** → pick a region → wait for it to provision (~1 min).

### 2b. Apply the SQL

Open **SQL Editor**, paste the contents of [`supabase/schema.sql`](./supabase/schema.sql), click **Run**. This creates the `img_bot` schema, grants, tables, trigger function, and the three Storage buckets.

You should see something like `Success. No rows returned.`

### 2c. Expose the schema to the API

**Project Settings → API → Exposed schemas.** Add `img_bot` to the list (keep `public, graphql_public`). Save.

Without this you get `permission denied for schema img_bot` from every API call.

### 2d. Grab your keys

**Project Settings → API:**
- `URL` → `SUPABASE_URL`
- `service_role` key (under "Project API keys") → `SUPABASE_SERVICE_KEY`

The service-role key bypasses RLS. Keep it server-side only.

---

## 3. `.env`

Create `.env` in the repo root:

```bash
GEMINI_API_KEY=your_gemini_key
ANTHROPIC_API_KEY=your_anthropic_key
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_SERVICE_KEY=your_service_role_key
```

A template is in `.env.example`.

---

## 4. Boot the dashboard

```bash
.venv/bin/imgbot serve
```

You'll see:
```
→ imgbot onboarding app at http://127.0.0.1:8000
INFO: Uvicorn running on http://127.0.0.1:8000
```

Open **http://127.0.0.1:8000/** in any browser.

Useful flags:
- `--port 9000` — different port
- `--host 0.0.0.0` — listen on all interfaces (LAN / ngrok)
- `--reload` — auto-restart on code changes (dev only)

---

## 5. Onboard a test tenant

On the `/` page:

| Field             | Example value |
|-------------------|---------------|
| Phone (E.164)     | `+919999999999` *(use a number you control on WhatsApp)* |
| Plan quota        | `5` *(low, for fast quota-exhaustion testing)* |
| Business name     | `Test Sweets` |
| Business type     | `traditional Indian sweet shop` |
| Location          | `Raipur, Chhattisgarh` |
| Language          | `English` |
| Tagline           | `Made with love since 1998` |
| Target audience   | `families and gift-buyers` |
| Tone              | `warm, festive, traditional` |
| Header text       | `Test Sweets` |
| Social handle     | `@testsweets` |
| Footer phone      | `MO. 9999999999` |
| Footer email      | `hello@testsweets.in` |
| Footer website    | `www.testsweets.in` |
| Theme BG          | pick a deep red / brown |
| Logo              | upload any transparent-PNG logo |
| Sample posters    | drop 2-3 reference posters (optional) |
| Inspiration       | `target Chhattisgarh families, warm earth tones, ghee + jaggery visual cues, NOT modern minimalism` |

Hit **Onboard tenant**. The button shows "Building system prompt with Claude…" while Sonnet 4.6 works (~10-20 s). The model emits the system prompt via a forced tool call so no narration / preamble can leak into the saved value. Trend awareness comes from Claude's training-time knowledge of the 2026 Indian festival calendar — no web searches, ~$0.05-0.10 per onboarding.

On success you get:

- `tenant_id` (uuid)
- the Supabase `logo_path`
- system prompt size (`~15-25K chars` is normal — it's bigger now because of the embedded trend calendar)
- a 600-char preview of the system prompt — scan it for a "TRENDS / FRESHNESS / CALENDAR" section that names real festivals and dates

### Verify in Supabase

In the SQL editor:
```sql
select id, phone, business->>'name' as biz, plan_quota, length(system_prompt) as prompt_chars
  from img_bot.tenants;
```
You should see your row.

In **Storage**, the `tenant-logos` bucket has `+919999999999/logo.png`; if you uploaded samples, `tenant-samples/+919999999999/sample_00.jpg`, etc.

---

## 6. Generate a poster from the CLI

```bash
.venv/bin/imgbot generate --phone "+919999999999"
```

Output:
```
→ idea  : Diwali sweet gift box
→ quota : 1  remaining 4
✓ Final poster -> /Users/.../data/tenants/+919999999999/posters/20260603_223315_diwali_sweet_gift_box.final.png
{"image_path": "...", "raw_path": "...", "idea_title": "Diwali sweet gift box", "quota_remaining": 4}
```

Open the `.final.png` — that's the branded poster (header + footer composited around the Gemini image).

### Inspect what landed in the DB

```bash
.venv/bin/imgbot tenants info "+919999999999"
```
shows the tenant + the most recent 10 posters.

Or via SQL:
```sql
select idea_title, length(detailed_prompt) as chars, status, created_at
  from img_bot.posters
 where tenant_id = (select id from img_bot.tenants where phone = '+919999999999')
 order by created_at desc;
```

### Run a few more to test diversity

Run `imgbot generate ...` 4 more times back-to-back. Verify:

- Each `idea_title` is distinct (the recent-history pool prevents repeats — last 12 carried into every call).
- Topic relevance, trend-leaning and brand fit all come from the per-tenant system prompt; runtime just provides date + history. If you'd like richer trend awareness, that's planned for phase 2.
- The 6th `imgbot generate` returns:
  ```
  {"error": "quota_exceeded", "message": "tenant ... is out of quota (5/5 used)"}
  ```
  Exit code 3.

### Reset the quota

```bash
.venv/bin/imgbot tenants set-quota "+919999999999" --quota-used 0
```

---

## 7. WhatsApp end-to-end

### 7a. Install the bot

```bash
cd whatsapp-bot
npm install
```

### 7b. Boot

```bash
npm start
```

A QR code prints in the terminal. On your phone:

1. WhatsApp → Settings → Linked devices → Link a device
2. Scan the QR code

Wait for `ready — bot wid: ...`.

### 7c. Test the flow

From the WhatsApp account you used as the test tenant's `phone`, **DM the bot** (do NOT add it to a group — the bot ignores groups) with exactly:

```
new poster
```

You should see:

1. Bot replies `⏳ Generating your poster…`
2. ~30-60 s later the bot replies with the branded poster image + the `idea_title` as caption + `(4 posters left this period)` line.

### 7d. Errors you might hit

| Error reply                                                   | Cause                                                                  |
|---------------------------------------------------------------|------------------------------------------------------------------------|
| `⚠️ You're not onboarded yet. Please contact your admin…`    | Sender's phone doesn't match any `img_bot.tenants.phone` row           |
| `⚠️ You've used up this period's quota. Reach out to admin…` | `quota_used >= plan_quota`                                             |
| `❌ Generation failed: …`                                     | Anything else — see the bot terminal for the full Python stderr        |

### 7e. Stop the bot

`Ctrl+C` in the bot terminal. The auth session is persisted under `whatsapp-bot/.wwebjs_auth/` so the next `npm start` skips the QR scan.

---

## 8. Operating tasks

### Refresh a tenant's trend awareness

The trend calendar is baked into the system prompt at onboarding and ages with the prompt. Every few months, refresh it by re-onboarding the tenant:

```sql
-- delete the existing row + cascade their posters
delete from img_bot.tenants where phone = '+91…';
```

Then resubmit the onboarding form. Opus runs fresh web searches and writes a new system prompt with an updated calendar. Same logo + sample posters + inspiration text — paste them back in.

### Reset a tenant's quota mid-month

```bash
.venv/bin/imgbot tenants set-quota "+91…" --quota-used 0
```

### Bump a tenant's plan size

```bash
.venv/bin/imgbot tenants set-quota "+91…" --plan-quota 20
```

### See every tenant

```bash
.venv/bin/imgbot tenants list
```

### Inspect a tenant's last 10 posters

```bash
.venv/bin/imgbot tenants info "+91…"
```

### Pull the full detailed_prompt for a recent poster (Supabase SQL)

```sql
select idea_title, detailed_prompt
  from img_bot.posters
 where tenant_id = '...'
 order by created_at desc
 limit 1;
```

Useful when an output looks off — compare against `tenants.system_prompt` and the runtime user template (`src/imgbot/pipeline/prompts/runtime.py`).

---

## 9. Troubleshooting

| Symptom                                                                  | Most likely cause / fix                                                                              |
|--------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------|
| `permission denied for schema img_bot`                                   | Step 2c (Exposed schemas) skipped, OR the grants block in `schema.sql` didn't run — re-paste it      |
| `RuntimeError: SUPABASE_URL is not set`                                  | `.env` missing or `imgbot` invoked from a directory without `.env` next to it                        |
| `Thinking may not be enabled when tool_choice forces tool use.`          | Old build of `src/imgbot/ai/claude.py` — the runtime call must use `thinking: {"type": "disabled"}` |
| `Image model returned no image. Model said: …`                           | Gemini refused the prompt (content policy) — re-run; if persistent, inspect the `detailed_prompt`    |
| Bot replies "not onboarded" but you DID onboard                          | The phone you onboarded with doesn't match the WhatsApp sender's normalized form. Check `tenants list` |
| Hindi text renders as boxes in the header                                | Devanagari font missing — `brew install libraqm` (rebuild Pillow if needed), or `apt install fonts-noto` |
| Logo has a white box around it on the header band                        | Logo isn't transparent. Either re-export with transparency or set `LOGO_REMOVE_BG=True` in `config`  |
| `tenant-posters` Storage bucket is empty after a successful generate     | Bucket wasn't created — `insert into storage.buckets` lines in `schema.sql` didn't run               |
| Form upload fails with 422 `business: Field required`                    | JavaScript disabled in the browser, or a CORS/proxy stripped the multipart body                      |
| `imgbot serve` exits immediately with `address already in use`           | Port 8000 occupied — pass `--port 8001` (or find + kill: `lsof -ti:8000 \| xargs kill`)              |

If a fresh server log helps, run `imgbot serve` with logs in foreground and reproduce. The relevant Python stack lands in the same terminal.

---

## 10. Cleanup

```bash
# stop bot (Ctrl+C)
# stop dashboard (Ctrl+C)

# delete a test tenant + its history:
psql "$SUPABASE_DB_URL" -c "delete from img_bot.tenants where phone = '+919999999999';"
# (posters cascade)

# remove cached local files:
rm -rf data/tenants/+919999999999/
```

For a full DB reset: drop the schema in the SQL editor (`drop schema img_bot cascade;`) and re-apply `schema.sql`.
