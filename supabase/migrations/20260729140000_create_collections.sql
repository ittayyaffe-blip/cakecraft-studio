-- CakeCraft Studio - cake collections (Birthday, Wedding, etc.)

create table if not exists public.collections (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  description text,
  image text,
  display_order integer not null default 0,
  active boolean not null default true,
  created_at timestamptz not null default now()
);

create index if not exists collections_active_display_order_idx
  on public.collections (active, display_order);

alter table public.collections enable row level security;

-- Seed the five initial collections (idempotent: skip rows that already exist)
insert into public.collections (name, description, image, display_order, active)
select v.name, v.description, v.image, v.display_order, true
from (
  values
    ('Birthday', 'Playful designs that celebrate another beautiful year.', 'cake-birthday.svg', 1),
    ('Wedding', 'Timeless elegance for your most cherished celebration.', 'cake-wedding.svg', 2),
    ('Baby Shower', 'Delicate sweetness to welcome new beginnings.', 'cake-babyshower.svg', 3),
    ('Graduation', 'Toast to achievement with a cake as bold as the milestone.', 'cake-graduation.svg', 4),
    ('Corporate', 'Sophisticated centerpieces for brand celebrations and events.', 'cake-corporate.svg', 5)
) as v(name, description, image, display_order)
where not exists (
  select 1 from public.collections c where c.name = v.name
);
