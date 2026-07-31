-- CakeCraft Studio - seed sample cake templates (3 per collection)
-- category matches the existing collections.name values (no collection_id yet)

insert into public.cake_templates (bakery_id, name, category, style, base_price, active)
select
  (select id from public.bakery where email = 'contact@maisondegateau.fr' limit 1),
  v.name, v.category, v.style, v.base_price, true
from (
  values
    ('Classic Vanilla Birthday', 'Birthday', 'Round', 45.00),
    ('Chocolate Confetti Celebration', 'Birthday', 'Round', 52.00),
    ('Rose Gold Number Cake', 'Birthday', 'Sculpted', 68.00),

    ('Ivory Three-Tier Classic', 'Wedding', 'Tiered', 320.00),
    ('Gold Leaf Romance', 'Wedding', 'Tiered', 380.00),
    ('Naked Cake Garden', 'Wedding', 'Semi-naked', 290.00),

    ('Soft Blush Blossom', 'Baby Shower', 'Round', 58.00),
    ('Little Feet Delight', 'Baby Shower', 'Round', 55.00),
    ('Storybook Baby Cloud', 'Baby Shower', 'Sculpted', 64.00),

    ('Cap & Diploma Classic', 'Graduation', 'Round', 60.00),
    ('Golden Achievement Cake', 'Graduation', 'Round', 62.00),
    ('Class of Photo Cake', 'Graduation', 'Sheet', 70.00),

    ('Brand Logo Sheet Cake', 'Corporate', 'Sheet', 75.00),
    ('Executive Monogram Cake', 'Corporate', 'Round', 66.00),
    ('Product Launch Centerpiece', 'Corporate', 'Tiered', 150.00)
) as v(name, category, style, base_price)
where not exists (
  select 1 from public.cake_templates c where c.name = v.name
);
