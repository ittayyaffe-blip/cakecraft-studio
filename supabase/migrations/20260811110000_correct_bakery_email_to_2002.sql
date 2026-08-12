-- CakeCraft Studio - correct the bakery's official contact email (again)
--
-- 20260811100000_update_bakery_email.sql changed the placeholder
-- 'contact@maisondegateau.fr' to 'mybestcake2022@gmail.com', based on an
-- incorrect assumption about which Gmail account was the real, configured
-- CakeCraft mailbox. That has since been definitively corrected: the
-- project owner has personally verified the Google Account, and the
-- existing production Gmail App Password authenticates successfully
-- against 'mybestcake2002@gmail.com', not '...2022@gmail.com'.
--
-- 20260811100000 is left untouched (historically correct for what it
-- did at the time) -- this is a new, forward-only correction, matching
-- this project's established convention of never editing an applied
-- migration.
--
-- Idempotent: only touches a row still holding the incorrect
-- 'mybestcake2022@gmail.com' value, so re-running this after it's
-- already applied is a no-op. Matches by email, not by id, for the same
-- reason 20260811100000 does. Touches only public.bakery.email -- no
-- other column, table, or row anywhere is affected.

update public.bakery
set email = 'mybestcake2002@gmail.com'
where email = 'mybestcake2022@gmail.com';
