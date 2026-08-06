-- CakeCraft Studio - Phase 1: staff identity + audit log
--
-- staff_profiles maps a Supabase Auth user (auth.users, managed entirely by
-- Supabase Auth) to an app-level role. Identity and password are never
-- duplicated here — this table only exists to answer "is this
-- already-authenticated user an active staff member, and what role do they
-- have?" (see backend/app/services/auth_service.py).
--
-- audit_log is the append-only record every admin action writes to via
-- backend/app/services/audit_service.py. Phase 1 only ever inserts
-- admin.login / admin.logout rows; the table is intentionally generic so
-- future admin actions (catalog edits, order status changes, etc.) log
-- into the same place without a schema change.

create table if not exists public.staff_profiles (
  user_id uuid primary key references auth.users (id) on delete cascade,
  name text not null,
  role text not null check (role in ('admin', 'staff')),
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists staff_profiles_role_idx
  on public.staff_profiles (role);

alter table public.staff_profiles enable row level security;

create table if not exists public.audit_log (
  id uuid primary key default gen_random_uuid(),
  actor_id uuid references public.staff_profiles (user_id) on delete set null,
  action text not null,
  entity_type text not null,
  entity_id uuid,
  before jsonb,
  after jsonb,
  created_at timestamptz not null default now()
);

create index if not exists audit_log_actor_id_idx
  on public.audit_log (actor_id);
create index if not exists audit_log_entity_idx
  on public.audit_log (entity_type, entity_id);
create index if not exists audit_log_created_at_idx
  on public.audit_log (created_at);

-- Lock both tables out of the Data API by default, matching every other
-- table in this project. The FastAPI backend uses the service-role key,
-- which bypasses RLS entirely (see 20260729120000_initial_schema.sql for
-- the same note on the original tables). Real per-role RLS policies are
-- future work, once it's decided which of this table's reads/writes should
-- also be enforced at the database layer rather than only in the backend.
alter table public.audit_log enable row level security;
