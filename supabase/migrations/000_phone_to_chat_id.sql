-- imgbot migration 000 — rename `phone` → `chat_id` on img_bot.tenants
--
-- The column was originally an E.164 phone (`+917974387273`). It's now a
-- WhatsApp chat ID — either `<digits>@c.us` (phone-based) or `<digits>@lid`
-- (Linked Identifier, privacy layer). This migration:
--   1. renames the column (only if `phone` still exists)
--   2. converts any pre-existing `+<digits>` values to `<digits>@c.us`
--
-- Idempotent — safe to re-run.

do $$
begin
  if exists (
    select 1 from information_schema.columns
     where table_schema = 'img_bot'
       and table_name   = 'tenants'
       and column_name  = 'phone'
  ) then
    alter table img_bot.tenants rename column phone to chat_id;
  end if;
end$$;

-- Upgrade any rows that still hold the legacy `+digits` form to a proper JID.
-- (No-op once everything is on the new format.)
update img_bot.tenants
   set chat_id = regexp_replace(chat_id, '^\+', '') || '@c.us'
 where chat_id !~ '@';
