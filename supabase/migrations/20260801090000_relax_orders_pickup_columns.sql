-- CakeCraft Studio - allow orders to be created before pickup scheduling exists
-- No milestone through Order Submission collects a pickup date/time yet;
-- making these nullable unblocks POST /orders without fabricating placeholder
-- values. Revert to NOT NULL once a pickup-scheduling step is implemented.

alter table public.orders alter column pickup_date drop not null;
alter table public.orders alter column pickup_time drop not null;
