-- CakeCraft Studio - point collections at the new hero photographs
-- Data-only update: replaces the placeholder SVG illustrations with the
-- real collection photos now in frontend/assets/images/. No schema change.

update public.collections set image = 'cake-birthday.png' where name = 'Birthday';
update public.collections set image = 'cake-wedding.png' where name = 'Wedding';
update public.collections set image = 'cake-babyshower.png' where name = 'Baby Shower';
update public.collections set image = 'cake-graduation.png' where name = 'Graduation';
update public.collections set image = 'cake-corporate.png' where name = 'Corporate';
