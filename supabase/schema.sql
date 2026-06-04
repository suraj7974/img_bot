-- imgbot — Supabase schema.
--
-- All app tables live under the `img_bot` schema rather than `public`, so
-- this project doesn't fight with anything else you put in the same Supabase
-- project later. Storage buckets stay where Supabase puts them (`storage.*`).
--
-- Apply once on a fresh Supabase project:
--   psql "$SUPABASE_DB_URL" -f supabase/schema.sql
-- or paste this whole file into the Supabase SQL editor.
--
-- ⚠️  ONE MANUAL STEP IN THE DASHBOARD
--   Supabase's PostgREST API only exposes `public` by default. To let the
--   service-role client read/write under `img_bot`:
--     Project Settings → API → "Exposed schemas"
--   add `img_bot` (keep `public, graphql_public` in there) and save.
--   Without this the Python code gets 404 / "schema not exposed" errors.
--
-- The Python code runs server-side with the service-role key and bypasses
-- RLS by design. We do NOT enable RLS on these tables — there is no public
-- frontend yet. Add policies later when self-serve onboarding ships.

create extension if not exists pgcrypto;  -- gen_random_uuid() lives in `public`

create schema if not exists img_bot;

-- Supabase's PostgREST API authenticates as `anon` / `authenticated` /
-- `service_role`. A fresh schema is owned by `postgres` and grants nothing to
-- those roles by default — without grants every API call returns 42501
-- "permission denied for schema img_bot". `service_role` is the only one our
-- code uses today, but granting all three matches Supabase's convention for
-- `public` and avoids surprises if you later expose tables under RLS.
grant usage on schema img_bot to anon, authenticated, service_role;
-- New objects created in this schema later get the same grants automatically.
alter default privileges in schema img_bot grant all on tables    to anon, authenticated, service_role;
alter default privileges in schema img_bot grant all on sequences to anon, authenticated, service_role;
alter default privileges in schema img_bot grant all on functions to anon, authenticated, service_role;

-- --------------------------------------------------------------------------
-- tenants — one row per paying customer
-- --------------------------------------------------------------------------
create table if not exists img_bot.tenants (
  id                  uuid primary key default gen_random_uuid(),
  phone               text not null,                     -- E.164, e.g. "+917974387273". Admin-typed, canonical identifier.
  chat_id             text,                              -- WhatsApp JID — `<digits>@c.us` or `<digits>@lid`. Auto-resolved by the bot on first DM. Never user-facing.
  business            jsonb not null,                    -- BusinessInfo
  brand               jsonb not null,                    -- BrandIdentity (dept_name, social_handle, footer_*)
  theme               jsonb not null,                    -- Theme (colours, ratios, language)
  logo_path           text not null,                     -- Storage path inside `tenant-logos`
  samples             jsonb not null default '[]'::jsonb,-- list of Storage paths under `tenant-samples`
  system_prompt       text not null,                     -- the Claude-generated per-tenant system prompt
  plan_quota          integer not null default 10,
  quota_used          integer not null default 0,
  quota_period_start  date not null default current_date,
  notes               text,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now()
);

create unique index if not exists tenants_phone_key on img_bot.tenants (phone);
create unique index if not exists tenants_chat_id_key
  on img_bot.tenants (chat_id) where chat_id is not null;

-- Idempotent cleanup for deployments that had the earlier short-lived
-- `trends_context` column. Trend awareness is now baked into the system
-- prompt at onboarding (via Opus + web search) rather than stored per-tenant.
alter table img_bot.tenants
  drop column if exists trends_context;

-- Keep `updated_at` honest on every UPDATE.
create or replace function img_bot.touch_updated_at() returns trigger as $$
begin
  new.updated_at := now();
  return new;
end;
$$ language plpgsql;

drop trigger if exists tenants_touch_updated_at on img_bot.tenants;
create trigger tenants_touch_updated_at
  before update on img_bot.tenants
  for each row execute function img_bot.touch_updated_at();

-- --------------------------------------------------------------------------
-- posters — one row per generated poster (history + audit trail)
-- --------------------------------------------------------------------------
create table if not exists img_bot.posters (
  id               uuid primary key default gen_random_uuid(),
  tenant_id        uuid not null references img_bot.tenants(id) on delete cascade,
  idea_title       text not null,         -- ≤8 words; surfaces as WhatsApp caption + fed into history
  detailed_prompt  text not null,         -- the full image-gen prompt Claude emitted
  image_path       text,                  -- Storage path under `tenant-posters` (final, branded)
  raw_path         text,                  -- Storage path under `tenant-posters` (pre-branding)
  status           text not null default 'done' check (status in ('done','failed')),
  error            text,
  created_at       timestamptz not null default now()
);

create index if not exists posters_tenant_created_idx
  on img_bot.posters (tenant_id, created_at desc);

-- --------------------------------------------------------------------------
-- pending_tenants — chat IDs that DM'd the bot but aren't onboarded yet.
-- Used as a self-service "inbox" so the admin can click-to-onboard without
-- having to dig through bot terminal logs.
-- --------------------------------------------------------------------------
create table if not exists img_bot.pending_tenants (
  chat_id        text primary key,
  last_message   text,
  message_count  integer not null default 1,
  first_seen_at  timestamptz not null default now(),
  last_seen_at   timestamptz not null default now()
);

create index if not exists pending_tenants_last_seen_idx
  on img_bot.pending_tenants (last_seen_at desc);

-- Re-grant explicitly on the tables/functions we just created so this file is
-- safe to re-apply on an existing schema even if default privileges were not
-- in place when those objects were originally created.
grant all on img_bot.tenants, img_bot.posters, img_bot.pending_tenants
  to anon, authenticated, service_role;
grant execute on function img_bot.touch_updated_at()
  to anon, authenticated, service_role;

-- --------------------------------------------------------------------------
-- Storage buckets — `storage.*` is its own namespace, no schema concept.
-- --------------------------------------------------------------------------
--   tenant-logos     — public read (logo URLs may be embedded in posters / shares)
--   tenant-samples   — private (sample posters supplied at onboarding)
--   tenant-posters   — private; generated posters are sent to WhatsApp via
--                      signed URL or downloaded server-side and forwarded.

insert into storage.buckets (id, name, public)
values ('tenant-logos',   'tenant-logos',   true)  on conflict (id) do nothing;
insert into storage.buckets (id, name, public)
values ('tenant-samples', 'tenant-samples', false) on conflict (id) do nothing;
insert into storage.buckets (id, name, public)
values ('tenant-posters', 'tenant-posters', false) on conflict (id) do nothing;
