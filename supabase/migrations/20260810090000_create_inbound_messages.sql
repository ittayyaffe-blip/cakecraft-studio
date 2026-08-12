-- CakeCraft Studio - Step 3: Inbound Customer Communication -> AI Agent + RAG
--
-- inbound_messages is a customer's incoming Email/WhatsApp message -- the
-- source/context an AI-drafted *outbound* reply is created from, never
-- itself part of the outbound approval workflow. Deliberately a separate
-- table from `notifications` (see 20260806090000_create_notifications.sql):
-- notifications' status check constraint and state machine
-- (queued/draft/awaiting_approval/approved/sent/failed, all enforced in
-- backend/app/services/notification_service.py) describe an *outbound*
-- message's lifecycle. An inbound message has a different lifecycle
-- entirely (received -> customer identified? -> order identified? -> AI
-- processed -> drafted/unable to answer/failed) -- forcing it into the
-- same table/state machine would mean either bending `notifications.status`
-- to mean two unrelated things, or adding inbound-only columns to a table
-- every existing outbound code path already relies on. A second small
-- table, linked via `draft_notification_id` once (if) a reply is drafted,
-- keeps both lifecycles independently correct.
--
-- No `direction` column: every row here is inbound by construction (the
-- table's own identity), so a column that would only ever hold one value
-- is unnecessary complexity, not schema completeness.

create table if not exists public.inbound_messages (
  id uuid primary key default gen_random_uuid(),

  -- Nullable: "no confident customer match" is a real, expected state
  -- (see backend/app/services/inbound_service.py) -- the message must
  -- still be visible to staff, not discarded or attached to a guessed
  -- identity. Never invent a customer row here.
  customer_id uuid references public.customers (id) on delete set null,

  -- Nullable + a separate status: "no matching order" and "multiple
  -- possible orders" are both real, different-from-each-other states a
  -- human needs to resolve -- collapsing them into "order_id is null"
  -- alone would lose that distinction.
  order_id uuid references public.orders (id) on delete set null,
  order_match_status text not null default 'none'
    check (order_match_status in ('matched', 'ambiguous', 'none')),

  channel text not null check (channel in ('email', 'whatsapp')),

  -- The provider's own message identifier (Gmail Message-Id header /
  -- WhatsApp Cloud API message id) -- the idempotency key: a webhook or
  -- IMAP poll retry must not create a duplicate row for the same real
  -- message. Unique per channel (the two providers' ID formats/spaces
  -- don't overlap, but scoping by channel is the more defensive key).
  provider_message_id text not null,

  -- Email: the References/In-Reply-To root, when present, for threading.
  -- WhatsApp: no true thread concept in the Cloud API -- left null.
  thread_id text,

  -- The raw sender identifier as received (email address or phone
  -- number), kept even when customer_id is null -- it's the one thing
  -- staff has to go on for an unmatched sender, and what a future
  -- "associate with a customer" action would search against.
  sender_identifier text not null,

  subject text,
  body text not null,
  received_at timestamptz not null,

  ai_status text not null default 'pending'
    check (ai_status in ('pending', 'processing', 'drafted', 'unable_to_answer', 'failed')),

  -- Set once (if) agent_service.draft_reply_to_inbound_message() creates
  -- an outbound draft -- the one link between this table and the existing
  -- notifications engine. Nullable: not every inbound message ends up
  -- with a draft (unknown customer, AI failure, "unable to answer").
  draft_notification_id uuid references public.notifications (id) on delete set null,

  created_at timestamptz not null default now()
);

-- Idempotency: a webhook retry or a re-run IMAP poll must resolve to the
-- same row, not a duplicate -- see backend/app/services/inbound_service.py.
create unique index if not exists inbound_messages_channel_provider_message_id_key
  on public.inbound_messages (channel, provider_message_id);

create index if not exists inbound_messages_customer_id_idx
  on public.inbound_messages (customer_id);
create index if not exists inbound_messages_order_id_idx
  on public.inbound_messages (order_id);
create index if not exists inbound_messages_ai_status_idx
  on public.inbound_messages (ai_status);
create index if not exists inbound_messages_created_at_idx
  on public.inbound_messages (created_at);

alter table public.inbound_messages enable row level security;

-- notifications.order_id was `not null` (see 20260806090000_create_
-- notifications.sql) because every existing creation path
-- (create_notification_for_order_event, agent_service.
-- draft_customer_communication) always has a real order to attach to.
-- An AI-drafted *reply* to an inbound message doesn't always have one --
-- the worked example in the Step 3 spec itself ("My daughter is turning
-- 8 next Saturday... what would you recommend?") is a prospective/general
-- question with no order at all. Widening to nullable is additive and
-- backward compatible: every existing row already has a real order_id, no
-- backfill needed, and both existing creation paths are unaffected (they
-- never pass null). Nothing about the status state machine, adapters, or
-- approval workflow changes.
alter table public.notifications alter column order_id drop not null;
