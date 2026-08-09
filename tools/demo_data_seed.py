#!/usr/bin/env python
"""CakeCraft Studio — ONE-TIME demo data seeder.

See docs/SPRINT2_DEMO_DATA.md for the original write-up and
docs/DATASET_SCALE_UP.md for the scale-up to ~2000 customers / ~2500
orders. In one paragraph: this populates the existing, unmodified
database with a realistic multi-year customer/order/notification history
— so the application reads like a bakery that's been operating
successfully for a few years — each order walked through a believable
status progression that generates real audit-log and notification-engine
events along the way.

This is NOT a synthetic-data framework and NOT a random generator. It is a
single script that calls the SAME service-layer functions the real
application already uses (order_service.create_order,
order_service.update_order_status, audit_service.record_event,
notification_service.*) — nothing here writes to the database any way the
app itself couldn't. Four of those functions gained a small, optional,
keyword-only timestamp-override parameter (see
docs/SPRINT2_DEMO_DATA.md "Backward compatibility") used *only* by this
script, so seeded records can be backdated across TOTAL_DAYS instead of
all landing on "today" — every real call site in the app is unaffected.

Order selection (who, what, when, how big) is deliberately split from
order creation (plan_orders() vs. seed_orders()) so the exact selection
logic that will run for real can also be run as a pure, offline
simulation — no database access at all — to sanity-check the projected
distribution against the target business-realism mix before spending the
time it takes to actually write it. See
`python tools/demo_data_seed.py --simulate`.

The write phase (seed_orders) runs concurrently across customers (see
MAX_WORKERS/_group_by_customer/_process_customer_chain) — at NUM_ORDERS
scale, the old fully-sequential approach would take hours; grouping every
customer's own orders into one sequential chain per worker, with many
chains running at once, gets a large real speedup without risking the
find-or-create-customer race a naive per-order parallelization would hit.

Usage (from anywhere, run with the project's venv):

    <path-to-venv>/python tools/demo_data_seed.py              # writes for real
    <path-to-venv>/python tools/demo_data_seed.py --simulate    # plans only, no DB access, prints projected distribution

Safe to re-run: every seeded customer's email ends in DEMO_EMAIL_DOMAIN, a
reserved, non-resolvable test domain no real customer could ever have.
Existing demo customers (and everything that cascades from them — their
orders and notifications) are deleted before reseeding. Real data is never
touched.
"""

import random
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

# This script lives in tools/, a sibling of backend/, not inside the
# backend package — make it importable before touching anything app.*.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.core.database import supabase  # noqa: E402
from app.services import audit_service, designer_service, notification_service, order_service, template_service  # noqa: E402

# --- Configuration -----------------------------------------------------

# Reserved for testing per RFC 2606 — can never resolve to a real domain,
# so no real customer could ever collide with it. This is the *entire*
# repeatability mechanism: any customer (and, transitively, any order or
# notification of theirs) whose email ends in this domain is demo data,
# full stop.
DEMO_EMAIL_DOMAIN = "demo.maisondegateau.test"

NUM_CUSTOMERS = 2000
NUM_ORDERS = 2500

# 3 years: the longest end of the requested "2-3 years" range, deliberately
# — more full annual seasonality cycles (3x Christmas, Valentine's, Mother's
# Day, wedding/graduation seasons) gives the ML forecasting pipeline a
# genuinely richer training signal than a single cycle would, directly
# serving "verify the forecasting pipeline continues to operate correctly."
TOTAL_DAYS = 365 * 3

# Fixed seed: reruns produce the same believable dataset rather than a
# different random one each time, matching "safe to run again" without
# needing to reason about a new random shape every time. This seeds the
# single-threaded PLANNING phase only (build_customer_pool through
# plan_orders) — the concurrent WRITE phase (seed_orders) never touches
# the global `random` module; see _process_customer_chain.
random.seed(20260807)

# Distinct base for each write-phase chain's own random.Random(BASE + i) —
# offset from the planning seed so the two aren't trivially correlated,
# though nothing depends on that; both are fixed for reproducibility.
WRITE_PHASE_SEED_BASE = 1_020_260_807

NOW = datetime.now(timezone.utc)

FIRST_NAMES = [
    "Sophie", "Camille", "Lucas", "Emma", "Louis", "Chloe", "Hugo", "Manon",
    "Nathan", "Lea", "Gabriel", "Ines", "Adam", "Jade", "Raphael", "Louise",
    "Arthur", "Alice", "Jules", "Zoe", "Ethan", "Sarah", "Noah", "Julia",
    "Liam", "Nina", "Mohamed", "Fatima", "Ahmed", "Amel", "Ivan", "Elena",
    "Marco", "Giulia", "James", "Olivia", "Wei", "Mei", "Yuki", "Kenji",
]

LAST_NAMES = [
    "Martin", "Bernard", "Dubois", "Thomas", "Robert", "Petit", "Durand",
    "Leroy", "Moreau", "Simon", "Laurent", "Lefebvre", "Michel", "Garcia",
    "David", "Bertrand", "Roux", "Vincent", "Fontaine", "Chevalier",
    "Rousseau", "Blanc", "Girard", "Andre", "Lefevre", "Mercier", "Dupont",
    "Lambert", "Bonnet", "Francois", "Martinez", "Legrand", "Garnier",
    "Faure", "Blanchard", "Gauthier", "Guerin", "Boyer", "Renard", "Perrin",
]

NOTE_TEMPLATES = {
    "Birthday": [
        "Please write 'Happy Birthday!' on the cake in gold icing.",
        "Kids' party — nothing too fragile please.",
        "Milestone birthday — would love a little extra sparkle.",
        None,
        None,
    ],
    "Wedding": [
        "Please match the sugar flowers to ivory and gold.",
        "Delivery to the venue the morning of, if possible.",
        "Tasting went great — same flavors as the sample please.",
        None,
    ],
    "Baby Shower": [
        "It's a boy! Soft blue accents if possible.",
        "It's a girl! Blush and gold theme.",
        "Gender reveal — please keep the inside a surprise!",
        None,
    ],
    "Graduation": [
        "Please include the graduation year on the cake.",
        "Our school colors are navy and gold if that's easy to work in.",
        None,
    ],
    "Corporate": [
        "Please deliver to office reception by 2pm.",
        "Include our logo on the cake if possible.",
        "Product launch event — clean, modern presentation please.",
        None,
    ],
}

# Refined per the business-realism pass: 60-70% Birthday, 10-15% Wedding,
# 10% Baby Shower, 5-10% Corporate, remainder (Graduation) miscellaneous.
# Only collections that actually have active templates are used (see
# main()) — category selection is intentionally independent of customer
# tier (see build_customer_tiers) so a VIP being picked more often can
# never skew this mix away from these targets.
COLLECTION_WEIGHTS = {
    "Birthday": 0.65,
    "Wedding": 0.12,
    "Baby Shower": 0.10,
    "Corporate": 0.07,
    "Graduation": 0.06,
}

# General month-to-month business variation, layered under the
# category-specific seasonality below (e.g. Wedding's own May-Sep boost) —
# a mild, bakery-wide "December is busy, January is quiet" pattern rather
# than a hard rule. 1.0 = baseline.
MONTH_WEIGHTS = {
    1: 0.80, 2: 0.90, 3: 1.00, 4: 1.00, 5: 1.10, 6: 1.10,
    7: 1.00, 8: 0.90, 9: 1.00, 10: 1.00, 11: 1.05, 12: 1.30,
}

# Named-occasion spikes, layered on top of MONTH_WEIGHTS rather than folded
# into it — each is a short, real window a bakery actually sees a rush
# around, not a whole-month effect. Valentine's Day in particular needs its
# own spike specifically *because* February's own MONTH_WEIGHT is below
# baseline (0.90): without this, the model would learn "February is quiet"
# and miss the real point spike around the 14th entirely.
def _mothers_day(year: int) -> date:
    """Second Sunday of May — the convention this catalog's other
    seasonality already assumes (see COLLECTION_WEIGHTS/category season)."""
    first = date(year, 5, 1)
    first_sunday = first + timedelta(days=(6 - first.weekday()) % 7)
    return first_sunday + timedelta(days=7)


def _holiday_multiplier(dt: datetime) -> float:
    d = dt.date()
    year = d.year
    if date(year, 12, 10) <= d <= date(year, 12, 24):  # Christmas run-up
        return 1.7
    if date(year, 2, 7) <= d <= date(year, 2, 14):  # Valentine's week
        return 1.9
    mothers_day = _mothers_day(year)
    if mothers_day - timedelta(days=6) <= d <= mothers_day:  # Mother's Day week
        return 1.6
    return 1.0


_MAX_MONTH_WEIGHT = max(MONTH_WEIGHTS.values())
_MAX_HOLIDAY_MULTIPLIER = 1.9
_MAX_COMBINED_WEIGHT = _MAX_MONTH_WEIGHT * _MAX_HOLIDAY_MULTIPLIER

# Relative pick-weight per customer tier — see build_customer_tiers(). A
# small VIP core accounts for a disproportionate share of orders (real
# loyal-customer economics), a mid-size regular group repeats
# occasionally, and the long tail orders once or twice.
TIER_WEIGHTS = {"vip": 14.0, "regular": 3.0, "occasional": 1.0}
VIP_FRACTION = 0.08
REGULAR_FRACTION = 0.27

# With 2-45 day pickup lead times spread across TOTAL_DAYS, an order's
# pickup date has almost always already passed by "now" — realistic for
# years of history (most of it SHOULD read as completed), but it leaves
# almost nothing in the active pipeline statuses (confirmed/in_progress/
# ready), which a live demo of the Orders screen / Production Board needs
# to show off. RECENT_ORDER_FRACTION reserves a slice of orders drawn from
# only the last RECENT_WINDOW_DAYS days, so their pickup dates naturally
# land at/after "now" — a believable current pipeline layered on top of a
# believable history, not instead of it.
#
# Scaled down from the original 1-year seeder's 0.10: that fraction was
# tuned against a 365-day TOTAL_DAYS, giving a ~1.8x density bump in the
# recent window versus the rest of history ("business is picking up," not
# an obvious spike). Kept at 0.10 with TOTAL_DAYS tripled and NUM_ORDERS
# ~7x larger, the same fixed 21-day window absorbs a proportionally much
# bigger slice — caught live via --simulate's monthly breakdown showing a
# single recent month at ~4x every other month. 0.035 restores roughly the
# same ~1.8x ratio at the new scale (verified via --simulate below) while
# still guaranteeing a genuinely lively current pipeline (~85 orders).
RECENT_ORDER_FRACTION = 0.035
RECENT_WINDOW_DAYS = 21

# The real order-status pipeline (order_service.ORDER_STATUSES), minus
# "pending" (every order starts there) and "cancelled" (handled as its
# own branch in progress_order). Maps onto the sprint brief's finer
# conceptual stages as: Confirmed -> confirmed; In Production, Decorating,
# and Quality Check -> in_progress (three conceptual sub-stages, one real
# status — orders.status has six values, not nine, and this sprint does
# not change that); Ready for Pickup -> ready; Completed -> completed.
# Notifications only exist for statuses notification_templates.py maps —
# all four of these do.
PROGRESSION = ["confirmed", "in_progress", "ready", "completed"]


def iso(dt: datetime) -> str:
    return dt.isoformat()


# --- Customer pool -------------------------------------------------------


def build_customer_pool(n: int = NUM_CUSTOMERS) -> list[dict]:
    """Pre-generate n realistic (name, email, phone) identities. Customers
    aren't inserted here — order_service.create_order's existing
    find-or-create-by-email logic creates each one the first time it's
    picked, and reuses it (a "repeat customer") every time after, exactly
    the way two real orders from the same person already work today.
    """
    used_emails: set[str] = set()
    customers = []
    while len(customers) < n:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}@{DEMO_EMAIL_DOMAIN}"
        if email in used_emails:
            email = f"{first.lower()}.{last.lower()}{len(customers)}@{DEMO_EMAIL_DOMAIN}"
        used_emails.add(email)
        phone = (
            f"+33 6 {random.randint(10, 99)} {random.randint(10, 99)} "
            f"{random.randint(10, 99)} {random.randint(10, 99)}"
        )
        customers.append({"name": f"{first} {last}", "email": email, "phone": phone})
    return customers


def build_customer_tiers(customers: list[dict]) -> list[str]:
    """Assign each customer a tier ("vip" / "regular" / "occasional") —
    three tiers instead of a flat repeat/non-repeat split, closer to how a
    real bakery's customer base actually looks: a small core of loyal
    regulars responsible for an outsized share of orders (the "some
    loyal/VIP customers with many historical orders" target), a mid-size
    group of occasional repeats, and a long tail who ordered once or
    twice. Returned as a parallel list (tiers[i] is customers[i]'s tier)
    rather than mutating the customer dicts — tier is a seeding-time
    concept only, never stored (no schema change; the real Customers
    screen already surfaces "loyal customer" via its own computed
    orderCount/lifetimeValue once real orders exist, so no separate VIP
    flag is needed anywhere).
    """
    n = len(customers)
    num_vip = max(1, int(n * VIP_FRACTION))
    num_regular = max(1, int(n * REGULAR_FRACTION))

    indices = list(range(n))
    random.shuffle(indices)
    vip_indices = set(indices[:num_vip])
    regular_indices = set(indices[num_vip : num_vip + num_regular])

    tiers = []
    for i in range(n):
        if i in vip_indices:
            tiers.append("vip")
        elif i in regular_indices:
            tiers.append("regular")
        else:
            tiers.append("occasional")
    return tiers


def pick_cake_size(cake_sizes: list[dict], tier: str) -> dict:
    """Different spending levels: VIP customers skew toward pricier
    sizes, everyone else picks uniformly. Sized by price_adjustment rank
    rather than hardcoded names ("Small"/"Large") so this keeps working
    if the catalog's size options are ever renamed.
    """
    if tier != "vip":
        return random.choice(cake_sizes)

    ordered = sorted(cake_sizes, key=lambda s: s.get("price_adjustment", 0))
    denom = max(len(ordered) - 1, 1)
    weights = [1.0 + 2.0 * (i / denom) for i in range(len(ordered))]
    return random.choices(ordered, weights=weights, k=1)[0]


# --- Dates ---------------------------------------------------------------


def nearest_weekend(dt: datetime) -> datetime:
    """Nudge forward to the nearest Fri/Sat/Sun (weekday 4/5/6)."""
    weekday = dt.weekday()
    if weekday >= 4:
        return dt
    return dt + timedelta(days=4 - weekday)


def _pick_days_ago_with_seasonal_bias() -> int:
    """Rejection-sample a days-ago value (0 to TOTAL_DAYS-1) so months with
    a higher MONTH_WEIGHTS multiplier (e.g. December) and dates inside a
    named-occasion window (_holiday_multiplier — Christmas run-up,
    Valentine's week, Mother's Day week) come up more often than a flat
    chance — simpler than mapping a chosen date back by hand, and easy to
    reason about: accept a random draw with probability proportional to
    its combined weight, else retry. .month/date() comparisons repeat
    naturally across all TOTAL_DAYS/365 years spanned, no year-aware logic
    needed here.
    """
    days_ago = 0
    for _ in range(8):
        days_ago = random.randint(0, TOTAL_DAYS - 1)
        candidate = NOW - timedelta(days=days_ago)
        combined_weight = MONTH_WEIGHTS[candidate.month] * _holiday_multiplier(candidate)
        if random.random() < combined_weight / _MAX_COMBINED_WEIGHT:
            return days_ago
    return days_ago  # bounded retries — accept whatever we last drew rather than looping forever


def random_order_datetime(category: str, recent: bool = False) -> datetime:
    """A created_at somewhere in the last TOTAL_DAYS (2-3 years), layering
    independent, soft biases rather than one statistically rigorous model —
    "believable rather than perfectly random":
      1. General month-to-month variation plus named-occasion spikes
         (MONTH_WEIGHTS + _holiday_multiplier — Christmas, Valentine's,
         Mother's Day — all categories) — skipped when `recent` (see
         RECENT_ORDER_FRACTION above): a recent order's date is drawn from
         the last RECENT_WINDOW_DAYS instead, so there's always a healthy,
         current pipeline to demo.
      2. Category-specific season: Wedding/Graduation resample toward
         their real-world season a couple of times (not a hard cutoff —
         some wedding cakes genuinely are ordered off-season). Skipped for
         `recent` orders too — an 18-day window is too narrow to
         meaningfully resample toward a season anyway.
      3. ~40% of non-Corporate orders nudge to the nearest weekend.
    """
    if recent:
        dt = NOW - timedelta(days=random.randint(0, RECENT_WINDOW_DAYS))
    else:
        days_ago = _pick_days_ago_with_seasonal_bias()
        dt = NOW - timedelta(days=days_ago)

        in_season_months = {"Wedding": (5, 6, 7, 8, 9), "Graduation": (5, 6)}.get(category)
        if in_season_months:
            for _ in range(2):
                if dt.month in in_season_months:
                    break
                days_ago = _pick_days_ago_with_seasonal_bias()
                dt = NOW - timedelta(days=days_ago)

    if category != "Corporate" and random.random() < 0.4:
        dt = nearest_weekend(dt)

    return dt.replace(hour=random.randint(9, 19), minute=random.choice([0, 15, 30, 45]), second=0, microsecond=0)


def pickup_datetime_for(order_dt: datetime, category: str) -> datetime:
    """A pickup date with a lead time proportional to how involved the
    cake typically is — weddings need weeks of notice, a birthday cake
    doesn't.
    """
    lead_days = {
        "Wedding": random.randint(14, 45),
        "Corporate": random.randint(3, 10),
    }.get(category, random.randint(2, 14))
    pickup = order_dt + timedelta(days=lead_days)
    return pickup.replace(hour=random.randint(10, 18), minute=random.choice([0, 30]), second=0, microsecond=0)


def choose_final_status(pickup_dt: datetime) -> str:
    """Where this order should end up, driven by how its pickup date
    relates to "now" — an order due six months ago should almost
    certainly be completed by now, not still pending. This is the crux of
    "believable rather than perfectly random."
    """
    if random.random() < 0.05:
        return "cancelled"

    days_until_pickup = (pickup_dt - NOW).days
    if days_until_pickup < -1:
        return "completed"
    if days_until_pickup <= 0:
        return random.choice(["ready", "completed"])
    if days_until_pickup <= 2:
        return random.choice(["in_progress", "ready"])
    if days_until_pickup <= 7:
        return random.choice(["confirmed", "in_progress"])
    return random.choice(["pending", "confirmed"])


def choose_note(category: str) -> str | None:
    return random.choice(NOTE_TEMPLATES.get(category, [None]))


# --- Planning: pure selection logic, no database access -------------------


def _assign_customer_indices(n_customers: int, weights: list[float], n_orders: int) -> list[int]:
    """One customer index per order, guaranteeing every customer appears
    at least once rather than leaving that to chance. Weighted random
    sampling alone (350 draws over 100 unevenly-weighted customers) left
    ~25 of the 100 pre-generated customers with zero orders in practice —
    they'd simply never be written to the database, undershooting the
    "100 customers" target. Instead: the first n_customers slots are each
    customer exactly once (order shuffled), and the remaining slots are
    filled by the same weighted sampling as before — so every customer is
    guaranteed a first order, and VIPs/regulars still rack up additional
    ones on top, same repeat-customer shape as before.
    """
    guaranteed = list(range(n_customers))
    random.shuffle(guaranteed)

    remaining = max(n_orders - n_customers, 0)
    extra = random.choices(range(n_customers), weights=weights, k=remaining) if remaining else []

    assignment = guaranteed + extra
    random.shuffle(assignment)  # so "everyone's first order" isn't front-loaded into the plan
    return assignment[:n_orders]


def plan_orders(customers: list[dict], tiers: list[str], templates_by_category: dict, designer_options: dict) -> list[dict]:
    """Decide everything about NUM_ORDERS orders — who, what, when, how
    big, and what status they'll end at — without writing anything
    anywhere. Kept separate from seed_orders() (which takes this plan and
    actually creates each order via the real services) specifically so
    the exact logic that will run for real can also run as a pure
    simulation: see --simulate and docs/SPRINT2_DEMO_DATA.md's Business
    Realism Report.
    """
    customer_weights = [TIER_WEIGHTS[tier] for tier in tiers]
    customer_indices = _assign_customer_indices(len(customers), customer_weights, NUM_ORDERS)
    categories = [c for c in COLLECTION_WEIGHTS if templates_by_category.get(c)]
    category_weights = [COLLECTION_WEIGHTS[c] for c in categories]

    plans = []
    for idx in customer_indices:
        customer, tier = customers[idx], tiers[idx]
        category = random.choices(categories, weights=category_weights, k=1)[0]
        template = random.choice(templates_by_category[category])
        cake_size = pick_cake_size(designer_options["cake_sizes"], tier)
        flavor = random.choice(designer_options["flavors"])
        filling = random.choice(designer_options["fillings"])
        frosting = random.choice(designer_options["frostings"])

        order_dt = random_order_datetime(category, recent=random.random() < RECENT_ORDER_FRACTION)
        pickup_dt = pickup_datetime_for(order_dt, category)
        final_status = choose_final_status(pickup_dt)

        plans.append(
            {
                "customer": customer,
                "customer_index": idx,  # groups a customer's orders into one write-phase chain — see _group_by_customer
                "customer_tier": tier,
                "category": category,
                "template": template,
                "cake_size": cake_size,
                "flavor": flavor,
                "filling": filling,
                "frosting": frosting,
                "order_dt": order_dt,
                "pickup_dt": pickup_dt,
                "final_status": final_status,
                "notes": choose_note(category),
            }
        )
    return plans


# --- Order status progression + notification engine -----------------------


def progress_notification_lifecycle(notification: dict, transition_dt: datetime, rng: random.Random) -> None:
    """Give a seeded notification a believable place in its own approval
    workflow instead of leaving every single one at "draft": if the
    status change it's for happened more than 3 days ago, walk it all the
    way to "sent" (a real bakery would have dealt with it by now); if it's
    recent, leave it at a random earlier stage — so the Notification Queue
    demo shows both a worked-through history and a live, actionable queue,
    not one or the other.

    Takes its own `rng` rather than using the global `random` module: this
    runs inside a ThreadPoolExecutor worker (see _process_customer_chain),
    and the shared global Random instance isn't safe for concurrent use
    from multiple threads — each chain gets its own, fully independent
    instance instead, deterministic and reproducible without any locking.
    """
    age_days = (NOW - transition_dt).days

    try:
        if age_days > 3:
            submitted = _call_with_retry(notification_service.submit_for_approval, notification)
            approved = _call_with_retry(notification_service.approve, submitted)
            sent_at = transition_dt + timedelta(hours=rng.randint(1, 6))
            _call_with_retry(notification_service.send, approved, sent_at=iso(sent_at))
            return

        stage = rng.choices(
            ["draft", "awaiting_approval", "approved"], weights=[0.6, 0.25, 0.15], k=1
        )[0]
        if stage in ("awaiting_approval", "approved"):
            notification = _call_with_retry(notification_service.submit_for_approval, notification)
        if stage == "approved":
            _call_with_retry(notification_service.approve, notification)
    except ValueError:
        # A transition guard rejected an unexpected notification state —
        # skip rather than let one odd row abort the whole seed run.
        pass


def progress_order(
    order_row: dict, final_status: str, order_dt: datetime, pickup_dt: datetime, rng: random.Random
) -> int:
    """Walk a freshly-created ('pending') order through the real status
    pipeline up to final_status, writing an audit_log entry and a
    notification for every step along the way — the same two things
    admin/orders.py's status-update route does for a real, staff-driven
    change, replicated here because the seeder calls services directly
    rather than going through HTTP (see docs/SPRINT2_DEMO_DATA.md).
    Returns how many notifications were created, for the run's summary.
    `rng` — see progress_notification_lifecycle's docstring.
    """
    if final_status == "pending":
        # choose_final_status's own "not due for a while yet" branch —
        # a real brand-new order that hasn't been touched since creation
        # has no status-change history at all, so there's nothing to
        # walk through. Caught live: PROGRESSION doesn't list "pending"
        # (create_order already leaves every order there), so indexing
        # into it here raised ValueError before this guard existed.
        return 0
    if final_status == "cancelled":
        # Realistic: cancelled either straight away, or after a
        # confirmation already went out.
        steps = ["cancelled"] if rng.random() < 0.5 else ["confirmed", "cancelled"]
    else:
        steps = PROGRESSION[: PROGRESSION.index(final_status) + 1]

    previous_status = "pending"
    current = order_row
    span_seconds = max((pickup_dt - order_dt).total_seconds(), 3600)
    notifications_created = 0

    for i, status in enumerate(steps):
        fraction = (i + 1) / (len(steps) + 1)
        transition_dt = order_dt + timedelta(seconds=span_seconds * fraction)
        if transition_dt > NOW:
            transition_dt = NOW - timedelta(minutes=rng.randint(1, 120))

        current = _call_with_retry(order_service.update_order_status, current["id"], status)

        _call_with_retry(
            audit_service.record_event,
            actor_id=None,  # system-generated, same convention real system events would use
            action="order.status_changed",
            entity_type="orders",
            entity_id=current["id"],
            before={"status": previous_status},
            after={"status": status},
            created_at=iso(transition_dt),
        )

        notification = _call_with_retry(
            notification_service.create_notification_for_order_event, current, status, created_at=iso(transition_dt)
        )
        if notification is not None:
            notifications_created += 1
            progress_notification_lifecycle(notification, transition_dt, rng)

        previous_status = status

    return notifications_created


# --- Repeatability ---------------------------------------------------------


def delete_existing_demo_data() -> None:
    """The whole repeatability story: find every customer tagged with the
    reserved demo email domain and delete them, and everything of theirs.
    Real customers can never match this filter.

    orders.customer_id is `on delete restrict` (protects real order
    history from accidental customer deletion — see the original schema
    migration), *not* cascade as originally assumed here: deleting a
    demo customer with existing orders was rejected by that FK
    constraint (caught live, mid-seed-run, against the real database).
    notifications.customer_id/order_id *are* `on delete cascade`, so
    deleting demo orders first takes their notifications with them, and
    only then can the now-orderless demo customers be deleted.
    """
    ids = _fetch_all_demo_customer_ids()
    if not ids:
        print("  No existing demo data found.")
        return

    # At NUM_CUSTOMERS scale, one `.in_(..., [...2000 uuids...])` DELETE
    # serializes into a GET-length query string long enough to risk a
    # URL-length limit (PostgREST DELETE filters, same as SELECT, travel
    # in the query string) — batched into chunks instead.
    batch_size = 200
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        supabase.table("orders").delete().in_("customer_id", batch).execute()
    for start in range(0, len(ids), batch_size):
        batch = ids[start : start + batch_size]
        supabase.table("customers").delete().in_("id", batch).execute()
    print(f"  Removed {len(ids)} previously-seeded demo customers and their orders/notifications.")


# --- Catalog ---------------------------------------------------------------


def group_templates_by_category(templates: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for template in templates:
        grouped.setdefault(template["category"], []).append(template)
    return grouped


# --- Writing the plan to the database --------------------------------------


def _seed_one_order(plan: dict, rng: random.Random) -> tuple[str | None, int]:
    """create_order + its full status progression for one plan. Returns
    (final_status or None if skipped, notifications_created).
    """
    order_id = _call_with_retry(
        order_service.create_order,
        {
            "template_id": plan["template"]["id"],
            "cake_size_id": plan["cake_size"]["id"],
            "flavor_id": plan["flavor"]["id"],
            "filling_id": plan["filling"]["id"],
            "frosting_id": plan["frosting"]["id"],
            "customer_name": plan["customer"]["name"],
            "customer_phone": plan["customer"]["phone"],
            "customer_email": plan["customer"]["email"],
            "notes": plan["notes"],
        },
        created_at=iso(plan["order_dt"]),
        pickup_date=plan["pickup_dt"].date().isoformat(),
        pickup_time=plan["pickup_dt"].time().isoformat(),
    )
    if order_id is None:
        return None, 0  # shouldn't happen (template id came straight from the DB), but never abort the run over one row

    order_row = _call_with_retry(order_service.get_order_by_id, order_id)
    notifications = progress_order(order_row, plan["final_status"], plan["order_dt"], plan["pickup_dt"], rng)
    return plan["final_status"], notifications


# A long-running run makes tens of thousands of HTTP requests (each order
# costs ~dozens across create_order's own catalog lookups plus every
# status-progression step). Two distinct transient failure modes caught
# live: (1) sequentially, one persistent connection's HTTP/2 stream count
# hits a hard ceiling and the server terminates it
# (httpcore.RemoteProtocolError); (2) concurrently, on Windows specifically,
# many threads sharing httpx's connection pool can hit
# `OSError: [WinError 10035] A non-blocking socket operation could not be
# completed immediately` (surfaces as httpx.ReadError/WriteError) under
# request bursts. Both clear on retry — httpx opens a fresh connection
# automatically on the next request.
_TRANSIENT_CONNECTION_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadTimeout,
    httpx.ReadError,
    httpx.WriteError,
    httpx.ConnectTimeout,
    httpx.PoolTimeout,
)
_MAX_CALL_ATTEMPTS = 4  # 1 initial + 3 retries


def _call_with_retry(fn, *args, **kwargs):
    """Retry a single service-layer call, not a whole multi-step order.
    Caught live: retrying the *entire* create_order-plus-progress_order
    sequence after a mid-chain connection drop could re-run create_order
    a second time for the same plan, leaving an extra, never-progressed
    "pending" order behind — the DB ended up with more orders than
    planned. Retrying each individual call in isolation instead means a
    transient drop only ever re-attempts the one write that actually
    failed, never re-creates something that already committed.
    """
    for attempt in range(_MAX_CALL_ATTEMPTS):
        try:
            return fn(*args, **kwargs)
        except _TRANSIENT_CONNECTION_ERRORS:
            if attempt == _MAX_CALL_ATTEMPTS - 1:
                raise
            time.sleep(0.2 * (attempt + 1))  # brief backoff, not an immediate hammer-retry

# I/O-bound HTTP work against Supabase/PostgREST — a thread pool, not more
# process/asyncio machinery, is the lazy-but-correct fit (httpx.Client,
# which supabase-py wraps, is documented safe for concurrent use from
# multiple threads). 2500 orders at the old sequential ~4.3s/order (mostly
# network latency, not CPU) would take ~3 hours — nowhere near "reasonable
# execution time" at this scale, so some concurrency is necessary, not
# optional. Chosen empirically against a small-scale live test (80 orders):
# 20 workers caused heavy `WinError 10035` socket contention in this
# environment (Windows + httpx's sync client, even with per-call retries —
# see _call_with_retry); 14 gave a real ~1.7x speedup over 8 with the same
# small, expected rate of retried/orphaned rows, and was the value actually
# used for the real run this file's numbers are from.
MAX_WORKERS = 14


def _group_by_customer(plans: list[dict]) -> dict[int, list[dict]]:
    """Every plan, grouped by customer_index and sorted chronologically
    within each group. This grouping is what makes parallelizing the write
    phase safe: order_service.create_order's find-or-create-by-email step
    has a classic check-then-insert race if two orders for the *same*
    customer ever ran in different threads at once (both could see "no
    customer yet" and insert two rows for one person). Processing each
    customer's whole order history sequentially, in one worker, while
    different customers run concurrently across workers, avoids the race
    entirely rather than needing a lock or a unique-constraint retry loop.
    """
    chains: dict[int, list[dict]] = defaultdict(list)
    for plan in plans:
        chains[plan["customer_index"]].append(plan)
    for chain in chains.values():
        chain.sort(key=lambda p: p["order_dt"])
    return chains


def _process_customer_chain(chain_index: int, chain_plans: list[dict]) -> tuple[Counter, int]:
    """Runs inside one ThreadPoolExecutor worker: one customer's entire
    order history, in order, sequentially — see _group_by_customer for why
    that scoping matters. Its own random.Random instance (see
    progress_notification_lifecycle's docstring) keeps this fully
    independent of every other concurrently-running chain.
    """
    rng = random.Random(WRITE_PHASE_SEED_BASE + chain_index)
    status_counts: Counter = Counter()
    total_notifications = 0

    for plan in chain_plans:
        # Retries already happen per-call, inside _seed_one_order's own
        # writes (see _call_with_retry) — by the time an exception reaches
        # here, every retry has already been exhausted, so this is just
        # "skip this one order, keep this customer's chain (and every
        # other chain) going" rather than another retry layer.
        try:
            final_status, notifications = _seed_one_order(plan, rng)
        except Exception as exc:
            print(f"  ...error seeding an order for customer_index={chain_index}, skipping: {exc}")
            continue

        if final_status is not None:
            total_notifications += notifications
            status_counts[final_status] += 1

    return status_counts, total_notifications


def seed_orders(plans: list[dict]) -> tuple[Counter, int]:
    """Actually create each planned order via the real service layer, then
    walk it through its status progression — one customer-chain at a time
    within a worker, many chains concurrently across workers (see
    MAX_WORKERS/_group_by_customer/_process_customer_chain). Returns
    (status_counts, total_notifications_created).
    """
    chains = _group_by_customer(plans)
    status_counts: Counter = Counter()
    total_notifications = 0
    orders_done = 0
    chains_done = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(_process_customer_chain, idx, chain_plans): idx
            for idx, chain_plans in chains.items()
        }
        for future in as_completed(futures):
            chain_status_counts, chain_notifications = future.result()
            status_counts.update(chain_status_counts)
            total_notifications += chain_notifications
            orders_done += sum(chain_status_counts.values())
            chains_done += 1

            if chains_done % 100 == 0:
                print(f"  ...{orders_done}/{NUM_ORDERS} orders seeded ({chains_done}/{len(chains)} customers processed)")

    return status_counts, total_notifications


def count_demo_customers() -> int:
    response = (
        supabase.table("customers")
        .select("id", count="exact", head=True)
        .ilike("email", f"%@{DEMO_EMAIL_DOMAIN}")
        .execute()
    )
    return response.count or 0


def _fetch_all_demo_customer_ids() -> list[str]:
    """Every demo customer id, paginated. PostgREST caps an unpaginated
    `.select()` response at a default max-rows (1000, in this project's
    case — caught live: NUM_CUSTOMERS=2000 meant this function's original
    single, unpaginated call silently returned only the first 1000 ids,
    which fed into count_demo_orders() and under-reported the real order
    total by roughly half). `.range()` pages through the full set.
    """
    ids: list[str] = []
    page_size = 1000
    start = 0
    while True:
        response = (
            supabase.table("customers")
            .select("id")
            .ilike("email", f"%@{DEMO_EMAIL_DOMAIN}")
            .range(start, start + page_size - 1)
            .execute()
        )
        ids.extend(row["id"] for row in response.data)
        if len(response.data) < page_size:
            break
        start += page_size
    return ids


def count_demo_orders() -> int:
    customer_ids = _fetch_all_demo_customer_ids()
    if not customer_ids:
        return 0

    # At NUM_CUSTOMERS scale, one `.in_(customer_id, [...2000 uuids...])`
    # call serializes into a GET query string long enough to risk hitting
    # a URL-length limit (PostgREST/the proxy in front of it) — batched
    # into chunks and summed instead, safely small either way.
    total = 0
    batch_size = 200
    for start in range(0, len(customer_ids), batch_size):
        batch = customer_ids[start : start + batch_size]
        response = (
            supabase.table("orders")
            .select("id", count="exact", head=True)
            .in_("customer_id", batch)
            .execute()
        )
        total += response.count or 0
    return total


# --- Reporting (shared by --simulate and a real run) -----------------------


def print_business_realism_report(plans: list[dict], tiers: list[str], customers: list[dict]) -> None:
    total = len(plans)
    by_category = Counter(p["category"] for p in plans)
    by_status = Counter(p["final_status"] for p in plans)
    by_month = Counter(p["order_dt"].strftime("%Y-%m") for p in plans)
    customer_order_counts = Counter(p["customer"]["email"] for p in plans)
    repeat_customers = sum(1 for count in customer_order_counts.values() if count > 1)
    tier_counts = Counter(tiers)

    print("\n--- Business Realism Report (projected from the plan) ---")
    print(f"Customers in pool: {len(customers)} ({dict(tier_counts)})")
    print(f"Orders planned: {total}")
    print("By category:")
    for category, count in by_category.most_common():
        print(f"  {category}: {count} ({count / total:.0%})")
    print("By status:")
    for status, count in by_status.most_common():
        print(f"  {status}: {count} ({count / total:.0%})")
    print(f"By month: {dict(sorted(by_month.items()))}")
    print(f"Customers with >1 order (repeat customers): {repeat_customers} of {len(customer_order_counts)} used")
    busiest = customer_order_counts.most_common(3)
    print(f"Busiest customers this plan: {busiest}")


def main() -> None:
    simulate = "--simulate" in sys.argv

    start = datetime.now()
    print("CakeCraft Studio — Demo Data Seeder" + (" (SIMULATION — no database writes)" if simulate else ""))
    print(f"Target: {NUM_CUSTOMERS} customers, {NUM_ORDERS} orders over the last {TOTAL_DAYS / 365:.0f} years\n")

    if not simulate:
        print("Step 1/4: Removing any previously-seeded demo data...")
        delete_existing_demo_data()
    else:
        print("Step 1/4: (skipped — simulation mode makes no database calls)")

    print("\nStep 2/4: Loading the existing catalog (templates, designer options)...")
    templates = template_service.get_active_templates()
    if not templates:
        print("ERROR: no active cake templates found in the database — nothing to seed orders against.")
        return

    templates_by_category = group_templates_by_category(templates)
    designer_options = designer_service.get_designer_options()
    missing = [key for key in ("cake_sizes", "flavors", "fillings", "frostings") if not designer_options[key]]
    if missing:
        print(f"ERROR: no active options found for: {', '.join(missing)} — cannot create valid orders.")
        return
    print(f"  {len(templates)} active templates across {len(templates_by_category)} collections")

    print("\nStep 3/4: Planning customers and orders...")
    customers = build_customer_pool()
    tiers = build_customer_tiers(customers)
    plans = plan_orders(customers, tiers, templates_by_category, designer_options)

    if simulate:
        print_business_realism_report(plans, tiers, customers)
        print(f"\nSimulation only — nothing was written. Elapsed: {(datetime.now() - start).total_seconds():.1f}s")
        return

    print("\nStep 4/4: Writing to the live database...")
    status_counts, total_notifications = seed_orders(plans)

    elapsed = (datetime.now() - start).total_seconds()
    actual_customers = count_demo_customers()
    actual_orders = count_demo_orders()

    print("\nDone.")
    print(f"  Customers now in the database with a demo email: {actual_customers}")
    print(f"  Orders now in the database for those customers: {actual_orders}")
    print(f"  Notifications created this run: {total_notifications}")
    print(f"  Orders by final status this run: {dict(status_counts)}")
    print(f"  Elapsed: {elapsed:.1f}s")
    print_business_realism_report(plans, tiers, customers)


if __name__ == "__main__":
    main()
