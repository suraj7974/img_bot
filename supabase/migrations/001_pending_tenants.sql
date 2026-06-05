-- imgbot migration 001 — pending_tenants inbox
--
-- Adds the table the WhatsApp bot writes to when an unknown chat_id sends
-- a DM, so the admin can click-to-onboard from the dashboard's /pending page
-- instead of digging through bot terminal logs.
--
-- Apply once on top of an existing img_bot deployment. Idempotent — safe to
-- re-run.

create table if not exists img_bot.pending_tenants (
  chat_id        text primary key,
  last_message   text,
  message_count  integer not null default 1,
  first_seen_at  timestamptz not null default now(),
  last_seen_at   timestamptz not null default now()
);

create index if not exists pending_tenants_last_seen_idx
  on img_bot.pending_tenants (last_seen_at desc);

-- Grant matching the rest of the schema. `service_role` is what the Python
-- code uses; anon/authenticated included for parity with the other tables
-- in case you ever expose this under RLS.
grant all on img_bot.pending_tenants
  to anon, authenticated, service_role;
