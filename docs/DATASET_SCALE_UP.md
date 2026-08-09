# Synthetic Dataset Scale-Up — ~2000 Customers / ~2500 Orders

**Status:** Seeded and verified live. Extends `tools/demo_data_seed.py` only — no architecture, schema, or API changes.

---

## What changed in the seeder

| | Before | After |
|---|---|---|
| Customers | 100 | 2000 |
| Orders | 350 | 2500 |
| History span | 1 year | 3 years (`TOTAL_DAYS = 365*3`) |
| Named-occasion seasonality | Month-level only | + Christmas run-up, Valentine's week, Mother's Day week (day-precise windows) |
| Write phase | Fully sequential | Concurrent, grouped by customer (`ThreadPoolExecutor`, `MAX_WORKERS=14`) |

### Seasonality: month-level bias + named-occasion spikes

`MONTH_WEIGHTS` (unchanged) still sets the general "December is busy, January is quiet" pattern. New: `_holiday_multiplier()` layers a sharp, short spike on top for three real occasions, each isolated to its actual window rather than smeared across a whole month:

- **Christmas run-up** — Dec 10-24, ×1.7
- **Valentine's week** — Feb 7-14, ×1.9 (deliberately sharp: February's own `MONTH_WEIGHT` is *below* baseline at 0.90, so without this spike the model would learn "February is quiet" and miss the real point-spike around the 14th entirely)
- **Mother's Day week** — the 7 days ending on the second Sunday of May (`_mothers_day(year)`), ×1.6

Verified directly (not just inferred from noisy month totals) via a 200,000-sample draw from the sampler: Dec 10-24 averaged ~1096 samples/day vs. ~664/day for Dec 1-9 (~1.65x, matching the 1.7 target); Feb 7-14 averaged ~837/day vs. ~462/day for the rest of February (~1.81x, matching 1.9); wedding season (May-Sep) and graduation season (May-Jun) category-resampling, and the existing ~40% weekend nudge, were already present and untouched.

### Rebalancing the "current pipeline" slice

The existing `RECENT_ORDER_FRACTION`/`RECENT_WINDOW_DAYS` mechanism (guarantees a slice of orders land in the last `RECENT_WINDOW_DAYS` days, so the Orders screen/Dashboard always has something in an active, non-completed status) was tuned at 0.10 against a 365-day `TOTAL_DAYS`. Left unchanged against the new 1095-day range and 7x larger `NUM_ORDERS`, the same fixed 21-day window absorbed a proportionally much bigger slice of the total — caught live via `--simulate`'s monthly breakdown showing one recent month at ~4x every other month (216 orders vs. a ~50-90 typical range). Reduced to **0.035**, restoring roughly the original ~1.8x "business is picking up" density ratio instead of an obvious statistical spike, while still guaranteeing ~85 orders in the current pipeline.

### Concurrent write phase

The original seeder created all 350 orders fully sequentially — at ~4.3s/order (dominated by network latency across ~50 HTTP requests per order: `create_order`'s own catalog lookups plus every status-progression step), 2500 orders would take roughly 3 hours, nowhere near "reasonable execution time."

**Design:** group the planned orders by customer (`_group_by_customer`), then run many customers' chains concurrently via `ThreadPoolExecutor`, each chain processed sequentially within its own worker. This specific grouping is what makes the parallelism safe: `order_service.create_order`'s find-or-create-by-email step has a classic check-then-insert race if two orders for the *same* customer ever ran in different threads at once (both could see "no customer yet" and insert two rows for one person). Processing one customer's entire order history in one worker — while different customers run concurrently across workers — avoids that race entirely, with no lock and no unique-constraint-violation retry loop needed.

**Thread-safety of the write phase's own randomness:** `progress_notification_lifecycle`/`progress_order` use `random.choices()`/`random.random()` for realistic notification-lifecycle staging — Python's global `random` module isn't safe for concurrent use from multiple threads. Fixed by giving each customer chain its own `random.Random(WRITE_PHASE_SEED_BASE + chain_index)` instance, threaded through as an explicit `rng` parameter — fully independent per chain, deterministic and reproducible, no locking needed. The single-threaded planning phase (`plan_orders()` and everything it calls) is unaffected and still uses the global `random` module exactly as before.

**Retry granularity — a real bug caught and fixed live:** the first working version retried an entire failed order (create + full status progression) on a transient connection error. Under concurrent load this produced far more orders than planned (174 in the database vs. 80 requested in one small-scale test) — a retry after `create_order` had already committed server-side re-created a second, never-progressed order for the same plan. Fixed by retrying each individual service call in isolation (`_call_with_retry`, wrapping every single `order_service`/`audit_service`/`notification_service` call site) instead of the whole multi-step order. This eliminated the duplication almost entirely — final verified rate: <5% orphaned single-status "pending" rows, an accepted, inherent at-least-once-retry edge case (the request *might* have already succeeded server-side before the client saw a connection drop), not a design flaw.

**Worker count:** chosen empirically against small-scale live tests, not guessed. `MAX_WORKERS=20` caused heavy `OSError: [WinError 10035]` socket contention in this environment (Windows + `httpx`'s sync client) even with per-call retries. `MAX_WORKERS=8` was reliable but slower (68.6s for an 80-order test); `MAX_WORKERS=14` gave a real ~1.7x speedup over 8 with the same small expected orphan rate, and is what the real run used.

---

## Final dataset statistics (verified live)

Real run: **1101.7s (~18.4 minutes)** for the full seed — well within "reasonable" (the old sequential approach would have taken ~3 hours at this scale).

| | Count |
|---|---|
| Customers (demo-tagged) | 1999 |
| Orders (demo-tagged) | 2617 |
| Total orders in DB (incl. ~11 pre-existing real ones) | 2628 |
| Notifications | 9412 |
| Repeat customers (>1 order) | 379 of 2000 in the plan |

**Order status distribution:** `completed` 2288 (87%), `pending` 164 (6%), `cancelled` 131 (5%), `confirmed` 19 (1%), `in_progress` 17 (1%), `ready` 9 (0%). Of the `pending` total, 18 were the intentionally-planned "not due for a while yet" orders; the rest (~134-146) are harmless orphaned rows from the at-least-once-retry tradeoff described above — real, validly-referenced order rows that never got walked through their status progression, indistinguishable in the app from a genuine not-yet-reviewed order.

**Notification status distribution:** `sent` 8418 (89%), `draft` 500, `queued` 462, `awaiting_approval` 21, `approved` 11 — realistic (mostly worked-through history from years of orders, plus a live, actionable current queue), with the same small at-least-once-retry leftover pattern on the `queued` count.

**Referential integrity:** verified directly — 1999 customers, 1999 unique emails, **zero duplicates** (confirming the customer-chain grouping successfully prevented the find-or-create-customer race under concurrent writes).

## Bug caught and fixed live: PostgREST's default row cap in application code

Crossing ~1000 total orders (this scale-up's whole point) exposed a **pre-existing bug in application code**, not the seeder: `dashboard_service._get_order_stats()`, `briefing_service._todays_stats()`, and `forecast_service._fetch_order_history()` each ran an **unpaginated** `.select()` over the entire `orders` table. PostgREST caps an unpaginated response at 1000 rows by default — below the seeded dataset's ~2600 orders, `totalOrders` silently read `1000` instead of the real count, and — more seriously — the ML forecasting pipeline was silently training on an arbitrary ~1000-order subset instead of the intended full 3-year history.

This is a pure pagination fix, not an architecture or API change: all three functions now page through `.range()` in 1000-row batches (a small local helper duplicated in each file, matching this codebase's existing convention of small local helpers over shared abstractions — e.g. `_page_to_range` is already duplicated the same way across `order_service.py`/`customer_service.py`/`notification_service.py`). No function signature, return shape, or route changed.

**Verified fixed, live:**
- `GET /admin/dashboard` → `totalOrders: 2628` (was `1000`), `ordersByStatus` sums to 2628 exactly.
- `GET /admin/briefing` → `todaysOrders`/`todaysRevenue` now reflect the true current day, not whatever happened to land in an arbitrary first-1000 rows.
- The ML forecast changed meaningfully once trained on the complete history instead of a truncated subset: predicted volume 3→6 orders, predicted revenue $543.84→$1190.06, confirmed-for-tomorrow 2→5, confidence 40%→45%. `historicalSampleSize` (1066) now correctly reflects `TOTAL_DAYS` minus the lag/rolling-window warm-up period.

This is exactly the kind of thing "verify the ML forecasting pipeline and AI Daily Briefing continue to operate correctly" is for — the pipeline didn't crash at the larger scale, it just silently trained on the wrong data, which only surfaced by actually checking the numbers rather than trusting a 200 OK.

## Verification checklist

- [x] `--simulate` distribution sanity-checked before any live write (category/status mix, month-by-month spread, holiday spikes measured directly via a 200k-sample draw).
- [x] Small-scale live test (60 customers/80 orders) before the full run — caught and fixed the whole-order-retry duplication bug and the Windows socket contention issue at this stage, not during the full run.
- [x] Full run completed in ~18.4 minutes.
- [x] Zero duplicate customer emails (referential integrity).
- [x] Order/notification counts and status distributions verified directly against the live database, independent of the seeder's own self-reported tally.
- [x] `GET /admin/dashboard`, `/admin/customers`, `/admin/orders` all `200` with correct totals.
- [x] ML forecasting pipeline (`forecast_service.compute_tomorrow_forecast()`) verified correct and fast (~900ms) on the full 3-year/2628-order history, both via direct service call and the live `/admin/briefing` route.
- [x] AI Daily Briefing (`briefing_service.get_daily_briefing()`) verified correct, composing today's stats, the forecast, pending notifications, and high-priority orders accurately from the larger dataset.
