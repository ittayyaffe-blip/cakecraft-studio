-- Seed the initial bakery (idempotent: skip if it already exists)

insert into public.bakery (name, email, phone, address)
select
  'Maison de Gâteau Paris',
  'contact@maisondegateau.fr',
  '+33 1 42 56 78 90',
  '15 Rue de Rivoli, Paris, France'
where not exists (
  select 1 from public.bakery where email = 'contact@maisondegateau.fr'
);
