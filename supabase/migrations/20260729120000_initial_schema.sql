-- CakeCraft Studio - initial schema
-- Tables: bakery, cake_templates, customization_options, customers, orders

create table if not exists public.bakery (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text not null,
  phone text,
  address text,
  created_at timestamptz not null default now()
);

create table if not exists public.cake_templates (
  id uuid primary key default gen_random_uuid(),
  bakery_id uuid not null references public.bakery (id) on delete cascade,
  name text not null,
  category text not null,
  style text not null,
  base_price numeric(10, 2) not null check (base_price >= 0),
  preview_image text,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists cake_templates_bakery_id_idx
  on public.cake_templates (bakery_id);

create table if not exists public.customization_options (
  id uuid primary key default gen_random_uuid(),
  template_id uuid not null references public.cake_templates (id) on delete cascade,
  type text not null,
  value text not null,
  price_adjustment numeric(10, 2) not null default 0,
  display_order integer not null default 0,
  active boolean not null default true
);

create index if not exists customization_options_template_id_idx
  on public.customization_options (template_id);

create table if not exists public.customers (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  email text not null,
  phone text,
  created_at timestamptz not null default now()
);

create table if not exists public.orders (
  id uuid primary key default gen_random_uuid(),
  customer_id uuid not null references public.customers (id) on delete restrict,
  template_id uuid not null references public.cake_templates (id) on delete restrict,
  pickup_date date not null,
  pickup_time time not null,
  status text not null default 'pending'
    check (status in ('pending', 'confirmed', 'in_progress', 'ready', 'completed', 'cancelled')),
  total_price numeric(10, 2) not null check (total_price >= 0),
  configuration jsonb not null default '{}'::jsonb,
  notes text,
  created_at timestamptz not null default now()
);

create index if not exists orders_customer_id_idx on public.orders (customer_id);
create index if not exists orders_template_id_idx on public.orders (template_id);
create index if not exists orders_pickup_date_idx on public.orders (pickup_date);
create index if not exists orders_status_idx on public.orders (status);

-- Lock every table out of the Data API by default. The FastAPI backend talks to
-- Postgres with the service role / a direct connection string, which bypasses RLS.
-- Add real policies here once end-user auth is introduced.
alter table public.bakery enable row level security;
alter table public.cake_templates enable row level security;
alter table public.customization_options enable row level security;
alter table public.customers enable row level security;
alter table public.orders enable row level security;
