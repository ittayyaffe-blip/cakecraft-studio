-- CakeCraft Studio - point all 15 cake templates at their new hero
-- photographs. Data-only update: replaces the generic hero-cake.svg
-- fallback with real photos now in frontend/assets/images/templates/.
-- No schema change.

update public.cake_templates set preview_image = 'templates/classic-vanilla-birthday-v1.png' where name = 'Classic Vanilla Birthday';
update public.cake_templates set preview_image = 'templates/chocolate-confetti-celebration-v1.png' where name = 'Chocolate Confetti Celebration';
update public.cake_templates set preview_image = 'templates/rose-gold-number-cake-v1.png' where name = 'Rose Gold Number Cake';
update public.cake_templates set preview_image = 'templates/cap-diploma-classic-v1.png' where name = 'Cap & Diploma Classic';
update public.cake_templates set preview_image = 'templates/class-of-photo-cake-v1.png' where name = 'Class of Photo Cake';
update public.cake_templates set preview_image = 'templates/executive-monogram-cake-v1.png' where name = 'Executive Monogram Cake';
update public.cake_templates set preview_image = 'templates/gold-leaf-romance-v1.png' where name = 'Gold Leaf Romance';
update public.cake_templates set preview_image = 'templates/golden-achievement-cake-v1.png' where name = 'Golden Achievement Cake';
update public.cake_templates set preview_image = 'templates/ivory-three-tier-classic-v1.png' where name = 'Ivory Three-Tier Classic';
update public.cake_templates set preview_image = 'templates/little-feet-delight-v1.png' where name = 'Little Feet Delight';
update public.cake_templates set preview_image = 'templates/luxury-abstract-corporate-celebration-v1.png' where name = 'Brand Logo Sheet Cake';
update public.cake_templates set preview_image = 'templates/naked-cake-garden-v1.png' where name = 'Naked Cake Garden';
update public.cake_templates set preview_image = 'templates/product-launch-centerpiece-v1.png' where name = 'Product Launch Centerpiece';
update public.cake_templates set preview_image = 'templates/soft-blush-blossom-v1.png' where name = 'Soft Blush Blossom';
update public.cake_templates set preview_image = 'templates/storybook-baby-cloud-v1.png' where name = 'Storybook Baby Cloud';
