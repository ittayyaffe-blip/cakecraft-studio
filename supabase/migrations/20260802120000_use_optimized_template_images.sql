-- CakeCraft Studio - point all 15 cake templates at their optimized WebP
-- photographs (960px wide, ~50-90KB each, down from ~2MB PNG originals).
-- Data-only update: no schema change. The matching .jpg fallback (same
-- basename) is served automatically by templates.js for browsers without
-- WebP support; the original .png files are left on disk, unreferenced.

update public.cake_templates set preview_image = 'templates/classic-vanilla-birthday-v1.webp' where name = 'Classic Vanilla Birthday';
update public.cake_templates set preview_image = 'templates/chocolate-confetti-celebration-v1.webp' where name = 'Chocolate Confetti Celebration';
update public.cake_templates set preview_image = 'templates/rose-gold-number-cake-v1.webp' where name = 'Rose Gold Number Cake';
update public.cake_templates set preview_image = 'templates/cap-diploma-classic-v1.webp' where name = 'Cap & Diploma Classic';
update public.cake_templates set preview_image = 'templates/class-of-photo-cake-v1.webp' where name = 'Class of Photo Cake';
update public.cake_templates set preview_image = 'templates/executive-monogram-cake-v1.webp' where name = 'Executive Monogram Cake';
update public.cake_templates set preview_image = 'templates/gold-leaf-romance-v1.webp' where name = 'Gold Leaf Romance';
update public.cake_templates set preview_image = 'templates/golden-achievement-cake-v1.webp' where name = 'Golden Achievement Cake';
update public.cake_templates set preview_image = 'templates/ivory-three-tier-classic-v1.webp' where name = 'Ivory Three-Tier Classic';
update public.cake_templates set preview_image = 'templates/little-feet-delight-v1.webp' where name = 'Little Feet Delight';
update public.cake_templates set preview_image = 'templates/luxury-abstract-corporate-celebration-v1.webp' where name = 'Brand Logo Sheet Cake';
update public.cake_templates set preview_image = 'templates/naked-cake-garden-v1.webp' where name = 'Naked Cake Garden';
update public.cake_templates set preview_image = 'templates/product-launch-centerpiece-v1.webp' where name = 'Product Launch Centerpiece';
update public.cake_templates set preview_image = 'templates/soft-blush-blossom-v1.webp' where name = 'Soft Blush Blossom';
update public.cake_templates set preview_image = 'templates/storybook-baby-cloud-v1.webp' where name = 'Storybook Baby Cloud';
