-- imgbot migration 002 — phone-as-primary, chat_id-as-resolved
--
-- After migration 000 we keyed tenants by WhatsApp chat_id. That forced the
-- admin to know an opaque @lid / @c.us string at onboarding time. New model:
--
--   * `phone`    — E.164 (`+917974387273`). This is what admin types and what
--                  uniquely identifies a tenant. NOT NULL + UNIQUE.
--   * `chat_id`  — populated by the bot on first contact via
--                  `client.getNumberId(phone)`. Nullable. Used as a fast
--                  reverse-lookup at runtime; never user-facing.
--
-- Apply once on top of 000 + 001. Idempotent.

-- 1) Add `phone` if missing.
alter table img_bot.tenants
  add column if not exists phone text;

-- 2) Backfill any rows from the legacy chat_id-as-phone form (`<digits>@c.us`).
--    @lid rows can't be backfilled (no derivable phone) — those rows will
--    need to have `phone` set manually OR be deleted + re-onboarded.
update img_bot.tenants
   set phone = '+' || regexp_replace(chat_id, '@c\.us$', '')
 where phone is null
   and chat_id like '%@c.us';

-- 3) Make `phone` the new identity column. Skip if it's already constrained.
do $$
begin
  if exists (
    select 1 from information_schema.columns
     where table_schema = 'img_bot'
       and table_name = 'tenants'
       and column_name = 'phone'
       and is_nullable = 'YES'
  ) then
    -- If any rows still have phone IS NULL (legacy @lid rows), this will fail.
    -- Clean those up first.
    alter table img_bot.tenants alter column phone set not null;
  end if;
end$$;

-- 4) Drop chat_id from being not-null — the bot fills it lazily now.
do $$
begin
  if exists (
    select 1 from information_schema.columns
     where table_schema = 'img_bot'
       and table_name = 'tenants'
       and column_name = 'chat_id'
       and is_nullable = 'NO'
  ) then
    alter table img_bot.tenants alter column chat_id drop not null;
  end if;
end$$;

-- 5) Unique constraints. `phone` is the user-facing identifier; `chat_id`
--    must still be unique when present (one WhatsApp account per tenant).
create unique index if not exists tenants_phone_key
  on img_bot.tenants (phone);

-- Drop the old chat_id PRIMARY-KEY-ish unique if it's blocking nulls.
-- (Postgres allows multiple NULLs on UNIQUE by default, so usually fine.)
do $$
begin
  if exists (
    select 1 from pg_indexes
     where schemaname = 'img_bot'
       and tablename  = 'tenants'
       and indexname  = 'tenants_chat_id_key'
  ) then
    -- already exists — leave it
    null;
  else
    create unique index tenants_chat_id_key
      on img_bot.tenants (chat_id)
      where chat_id is not null;
  end if;
end$$;
