-- CakeCraft Studio - correct the bakery's official contact email
--
-- The original seed (20260729130000_seed_bakery.sql) used
-- 'contact@maisondegateau.fr', a placeholder that was never actually
-- created as a real mailbox. The authoritative, real customer
-- communication address is 'mybestcake2022@gmail.com' -- see the Step 1
-- "Fix the Official Customer Communication Email" audit.
--
-- Idempotent: only touches a row still holding the old placeholder value,
-- so re-running this migration after it's already applied is a no-op.
-- Matches by email (like the seed migration itself does), not by id, so
-- it stays correct even if the bakery row's id ever differs across
-- environments.

update public.bakery
set email = 'mybestcake2022@gmail.com'
where email = 'contact@maisondegateau.fr';
