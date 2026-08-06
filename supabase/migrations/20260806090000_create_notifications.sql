-- CakeCraft Studio - Event-Driven Customer Communication Platform
--
-- notifications is the channel-agnostic queue + human-approval workflow
-- described in docs/SPRINT1_EVENT_DRIVEN_COMMUNICATION.md. One row is
-- created per customer-relevant order-status transition (see
-- backend/app/services/notification_service.py), then moves through:
--
--   queued -> draft -> awaiting_approval -> approved -> sent
--
-- (delivered / failed are reserved now for a future real channel adapter
-- to report back into, without a schema change when that day comes.)
--
-- This table intentionally covers what Master_Blueprint_v1.md §7 had
-- originally sketched as a separate `notifications_log` table too: once a
-- notification reaches `sent`, this same row already carries everything a
-- delivery log would need (channel, sent_at, provider_message_id) — a
-- second table would only duplicate it. `channel`/`provider_message_id`
-- stay nullable and unused until a real channel adapter sends something
-- (Sprint 3 adds the first one, Gmail); that nullability *is*
-- "channel-agnostic," expressed at the schema level.
--
-- No `approved_by` column: who approved/sent/edited a notification is
-- recorded in `audit_log` (see notification.* actions in
-- app/api/routes/admin/notifications.py), the same way order status
-- changes are — not duplicated onto this table.
--
-- Sprint 3 update (still pre-apply, so editing this file directly rather
-- than adding a second migration): added `provider_message_id`, the one
-- column the original design was missing to fully match what
-- Master_Blueprint_v1.md §7 sketched for a delivery log.

create table if not exists public.notifications (
  id uuid primary key default gen_random_uuid(),
  order_id uuid not null references public.orders (id) on delete cascade,
  customer_id uuid not null references public.customers (id) on delete cascade,
  event text not null,
  channel text,
  status text not null default 'queued'
    check (status in ('queued', 'draft', 'awaiting_approval', 'approved', 'sent', 'delivered', 'failed')),
  subject text,
  body text,
  provider_message_id text,
  sent_at timestamptz,
  created_at timestamptz not null default now()
);

create index if not exists notifications_order_id_idx
  on public.notifications (order_id);
create index if not exists notifications_customer_id_idx
  on public.notifications (customer_id);
create index if not exists notifications_status_idx
  on public.notifications (status);
create index if not exists notifications_created_at_idx
  on public.notifications (created_at);

-- Lock this table out of the Data API by default, matching every other
-- table in this project. The FastAPI backend uses the service-role key,
-- which bypasses RLS entirely (see 20260729120000_initial_schema.sql).
alter table public.notifications enable row level security;
