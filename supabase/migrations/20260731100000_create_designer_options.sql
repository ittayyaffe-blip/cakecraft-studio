-- CakeCraft Studio - Cake Designer lookup options (sizes, flavors, fillings, frostings)

create table if not exists public.cake_sizes (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  display_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists cake_sizes_active_display_order_idx
  on public.cake_sizes (active, display_order);

alter table public.cake_sizes enable row level security;

create table if not exists public.flavors (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  display_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists flavors_active_display_order_idx
  on public.flavors (active, display_order);

alter table public.flavors enable row level security;

create table if not exists public.fillings (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  display_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists fillings_active_display_order_idx
  on public.fillings (active, display_order);

alter table public.fillings enable row level security;

create table if not exists public.frostings (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  display_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists frostings_active_display_order_idx
  on public.frostings (active, display_order);

alter table public.frostings enable row level security;

-- Seed realistic default options (idempotent: skip rows that already exist)
insert into public.cake_sizes (name, display_order, active)
select v.name, v.display_order, true
from (values ('Small', 1), ('Medium', 2), ('Large', 3)) as v(name, display_order)
where not exists (select 1 from public.cake_sizes c where c.name = v.name);

insert into public.flavors (name, display_order, active)
select v.name, v.display_order, true
from (values ('Vanilla', 1), ('Chocolate', 2), ('Red Velvet', 3)) as v(name, display_order)
where not exists (select 1 from public.flavors c where c.name = v.name);

insert into public.fillings (name, display_order, active)
select v.name, v.display_order, true
from (values ('Strawberry', 1), ('Chocolate Ganache', 2), ('Lemon Curd', 3)) as v(name, display_order)
where not exists (select 1 from public.fillings c where c.name = v.name);

insert into public.frostings (name, display_order, active)
select v.name, v.display_order, true
from (values ('Buttercream', 1), ('Cream Cheese', 2), ('Dark Chocolate Ganache', 3)) as v(name, display_order)
where not exists (select 1 from public.frostings c where c.name = v.name);
