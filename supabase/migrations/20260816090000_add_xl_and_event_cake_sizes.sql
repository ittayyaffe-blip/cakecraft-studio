-- CakeCraft Studio - Servings + Event Pricing: add XL/Event serving bands
-- to the existing cake_sizes lookup table, and align Small/Medium/Large's
-- own servings_min/max with the newly approved guest-count band
-- boundaries (SMALL 8-12, MEDIUM 13-20, LARGE 21-30) -- purely
-- descriptive metadata, not a structural change: no order references
-- these numbers directly (orders store cake_size_id), so no historical
-- order is affected. Price adjustments continue the exact existing
-- linear +$50-per-tier pattern (Small +0, Medium +50, Large +100) ->
-- XL +150, Event +200.

update public.cake_sizes set servings_min = 8, servings_max = 12 where name = 'Small';
update public.cake_sizes set servings_min = 13, servings_max = 20 where name = 'Medium';
update public.cake_sizes set servings_min = 21, servings_max = 30 where name = 'Large';

insert into public.cake_sizes (name, display_order, active, price_adjustment, servings_min, servings_max)
select 'XL', 4, true, 150, 31, 50
where not exists (select 1 from public.cake_sizes where name = 'XL');

insert into public.cake_sizes (name, display_order, active, price_adjustment, servings_min, servings_max)
select 'Event', 5, true, 200, 51, 75
where not exists (select 1 from public.cake_sizes where name = 'Event');
