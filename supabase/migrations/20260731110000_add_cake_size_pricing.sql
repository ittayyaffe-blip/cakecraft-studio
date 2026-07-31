-- CakeCraft Studio - pricing and serving info for cake sizes

alter table public.cake_sizes
  add column if not exists price_adjustment integer not null default 0,
  add column if not exists servings_min integer,
  add column if not exists servings_max integer;

update public.cake_sizes
  set price_adjustment = 0, servings_min = 8, servings_max = 10
  where name = 'Small';

update public.cake_sizes
  set price_adjustment = 50, servings_min = 12, servings_max = 15
  where name = 'Medium';

update public.cake_sizes
  set price_adjustment = 100, servings_min = 18, servings_max = 22
  where name = 'Large';
