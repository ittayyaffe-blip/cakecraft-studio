-- CakeCraft Studio - Step 3B: Communication Intelligence & Guardrails
--
-- Extends the existing inbound_messages table (Step 3, see
-- 20260810090000_create_inbound_messages.sql) with the AI Agent's own
-- structured analysis of each message -- intent classification, the
-- application's risk-handling decision, why (if applicable) a human
-- needs to review it, and which bakery-knowledge sources grounded the
-- draft. Added to the existing table rather than a new parallel one, per
-- the same reasoning the Step 3 migration already established: this is
-- more detail about the same inbound-message record, not a new kind of
-- entity.
--
-- `intent` and `handling` are set by application code
-- (backend/app/services/agent_service.py's draft_reply_to_inbound_
-- message), never written directly from Claude's own free text: Claude's
-- classification is validated against a fixed set first (see
-- agent_service.INTENTS), and `handling` is a *separate*, app-owned risk
-- decision layered on top of intent (see agent_service.DEFAULT_HANDLING
-- / _compute_handling) -- Claude never decides handling itself, only
-- ever contributes a self-assessed signal that can push it more
-- cautious, never less. All four columns nullable: existing Step 3 rows
-- predate this feature and have none of them; every row this feature
-- processes going forward always gets all four.

alter table public.inbound_messages
  add column if not exists intent text,
  add column if not exists handling text check (handling in ('green', 'yellow', 'red')),
  add column if not exists review_reason text,
  add column if not exists knowledge_sources jsonb;

-- Supports a future "show me everything needing human judgment" filter
-- on the Communications workspace -- cheap to add now, alongside the
-- column it indexes, rather than as a separate later migration.
create index if not exists inbound_messages_handling_idx
  on public.inbound_messages (handling);
