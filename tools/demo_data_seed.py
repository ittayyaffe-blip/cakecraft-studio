#!/usr/bin/env python
"""CakeCraft Studio — ONE-TIME demo data seeder.

See docs/SPRINT2_DEMO_DATA.md for the full write-up. In one paragraph:
this populates the existing, unmodified database with ~100 customers and
~350 orders spread realistically over the last 12 months — so the
application reads like a bakery that's been operating successfully for
about a year — each walked through a believable status progression that
generates real audit-log and notification-engine events along the way.

This is NOT a synthetic-data framework and NOT a random generator. It is a
single script that calls the SAME service-layer functions the real
application already uses (order_service.create_order,
order_service.update_order_status, audit_service.record_event,
notification_service.*) — nothing here writes to the database any way the
app itself couldn't. Four of those functions gained a small, optional,
keyword-only timestamp-override parameter (see
docs/SPRINT2_DEMO_DATA.md "Backward compatibility") used *only* by this
script, so seeded records can be backdated across the last year instead of
all landing on "today" — every real call site in the app is unaffected.

Order selection (who, what, when, how big) is deliberately split from
order creation (plan_orders() vs. seed_orders()) so the exact selection
logic that will run for real can also be run as a pure, offline
simulation — no database access at all — to sanity-check the projected
distribution against the target business-realism mix before spending the
~15-25 minutes it takes to actually write it. See
`python tools/demo_data_seed.py --simulate`.

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
from collections import Counter
from datetime import datetime, timedelta, timezone
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

NUM_CUSTOMERS = 100
NUM_ORDERS = 350

# Fixed seed: reruns produce the same believable dataset rather than a
# different random one each time, matching "safe to run again" without
# needing to reason about a new random shape every time.
random.seed(20260807)

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
_MAX_MONTH_WEIGHT = max(MONTH_WEIGHTS.values())

# Relative pick-weight per customer tier — see build_customer_tiers(). A
# small VIP core accounts for a disproportionate share of orders (real
# loyal-customer economics), a mid-size regular group repeats
# occasionally, and the long tail orders once or twice.
TIER_WEIGHTS = {"vip": 14.0, "regular": 3.0, "occasional": 1.0}
VIP_FRACTION = 0.08
REGULAR_FRACTION = 0.27

# With 2-45 day pickup lead times spread across a full year, an order's
# pickup date has almost always already passed by "now" — realistic for a
# year of history (most of it SHOULD read as completed), but it leaves
# almost nothing in the active pipeline statuses (confirmed/in_progress/
# ready), which a live demo of the Orders screen / Production Board needs
# to show off. RECENT_ORDER_FRACTION reserves a slice of orders drawn from
# only the last RECENT_WINDOW_DAYS days, so their pickup dates naturally
# land at/after "now" — a believable current pipeline layered on top of a
# believable history, not instead of it.
RECENT_ORDER_FRACTION = 0.10
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


def _pick_days_ago_with_month_bias() -> int:
    """Rejection-sample a days-ago value (0-364) so months with a higher
    MONTH_WEIGHTS multiplier (e.g. December) come up more often than a
    flat 1/365 chance — simpler than mapping a chosen month back onto a
    specific date by hand, and easy to reason about: accept a random draw
    with probability proportional to that month's weight, else retry.
    """
    days_ago = 0
    for _ in range(8):
        days_ago = random.randint(0, 364)
        month = (NOW - timedelta(days=days_ago)).month
        if random.random() < MONTH_WEIGHTS[month] / _MAX_MONTH_WEIGHT:
            return days_ago
    return days_ago  # bounded retries — accept whatever we last drew rather than looping forever


def random_order_datetime(category: str, recent: bool = False) -> datetime:
    """A created_at somewhere in the last 12 months, layering independent,
    soft biases rather than one statistically rigorous model —
    "believable rather than perfectly random":
      1. General month-to-month variation (MONTH_WEIGHTS, all categories) —
         skipped when `recent` (see RECENT_ORDER_FRACTION above): a recent
         order's date is drawn from the last RECENT_WINDOW_DAYS instead,
         so there's always a healthy, current pipeline to demo.
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
        days_ago = _pick_days_ago_with_month_bias()
        dt = NOW - timedelta(days=days_ago)

        in_season_months = {"Wedding": (5, 6, 7, 8, 9), "Graduation": (5, 6)}.get(category)
        if in_season_months:
            for _ in range(2):
                if dt.month in in_season_months:
                    break
                days_ago = _pick_days_ago_with_month_bias()
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


def progress_notification_lifecycle(notification: dict, transition_dt: datetime) -> None:
    """Give a seeded notification a believable place in its own approval
    workflow instead of leaving every single one at "draft": if the
    status change it's for happened more than 3 days ago, walk it all the
    way to "sent" (a real bakery would have dealt with it by now); if it's
    recent, leave it at a random earlier stage — so the Notification Queue
    demo shows both a worked-through history and a live, actionable queue,
    not one or the other.
    """
    age_days = (NOW - transition_dt).days

    try:
        if age_days > 3:
            submitted = notification_service.submit_for_approval(notification)
            approved = notification_service.approve(submitted)
            sent_at = transition_dt + timedelta(hours=random.randint(1, 6))
            notification_service.send(approved, sent_at=iso(sent_at))
            return

        stage = random.choices(
            ["draft", "awaiting_approval", "approved"], weights=[0.6, 0.25, 0.15], k=1
        )[0]
        if stage in ("awaiting_approval", "approved"):
            notification = notification_service.submit_for_approval(notification)
        if stage == "approved":
            notification_service.approve(notification)
    except ValueError:
        # A transition guard rejected an unexpected notification state —
        # skip rather than let one odd row abort the whole seed run.
        pass


def progress_order(order_row: dict, final_status: str, order_dt: datetime, pickup_dt: datetime) -> int:
    """Walk a freshly-created ('pending') order through the real status
    pipeline up to final_status, writing an audit_log entry and a
    notification for every step along the way — the same two things
    admin/orders.py's status-update route does for a real, staff-driven
    change, replicated here because the seeder calls services directly
    rather than going through HTTP (see docs/SPRINT2_DEMO_DATA.md).
    Returns how many notifications were created, for the run's summary.
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
        steps = ["cancelled"] if random.random() < 0.5 else ["confirmed", "cancelled"]
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
            transition_dt = NOW - timedelta(minutes=random.randint(1, 120))

        current = order_service.update_order_status(current["id"], status)

        audit_service.record_event(
            actor_id=None,  # system-generated, same convention real system events would use
            action="order.status_changed",
            entity_type="orders",
            entity_id=current["id"],
            before={"status": previous_status},
            after={"status": status},
            created_at=iso(transition_dt),
        )

        notification = notification_service.create_notification_for_order_event(
            current, status, created_at=iso(transition_dt)
        )
        if notification is not None:
            notifications_created += 1
            progress_notification_lifecycle(notification, transition_dt)

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
    existing = (
        supabase.table("customers")
        .select("id")
        .ilike("email", f"%@{DEMO_EMAIL_DOMAIN}")
        .execute()
    )
    ids = [row["id"] for row in existing.data]
    if not ids:
        print("  No existing demo data found.")
        return

    supabase.table("orders").delete().in_("customer_id", ids).execute()
    supabase.table("customers").delete().in_("id", ids).execute()
    print(f"  Removed {len(ids)} previously-seeded demo customers and their orders/notifications.")


# --- Catalog ---------------------------------------------------------------


def group_templates_by_category(templates: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = {}
    for template in templates:
        grouped.setdefault(template["category"], []).append(template)
    return grouped


# --- Writing the plan to the database --------------------------------------


def _seed_one_order(plan: dict) -> tuple[str | None, int]:
    """create_order + its full status progression for one plan. Returns
    (final_status or None if skipped, notifications_created).
    """
    order_id = order_service.create_order(
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

    order_row = order_service.get_order_by_id(order_id)
    notifications = progress_order(order_row, plan["final_status"], plan["order_dt"], plan["pickup_dt"])
    return plan["final_status"], notifications


# A long-running run makes tens of thousands of sequential HTTP requests
# over one persistent connection (each order costs ~dozens of requests
# across create_order's own catalog lookups plus every status-progression
# step) — caught live, twice, reliably failing at the exact same point:
# the connection's underlying HTTP/2 stream count hits a hard ceiling and
# the server terminates it (httpcore.RemoteProtocolError). httpx opens a
# fresh connection automatically on the next request, so retrying the
# same plan once clears it. Accepted tradeoff: if the drop happens after
# create_order already committed but before progress_order finishes, the
# retry's create_order call makes one extra order for that plan — fine
# for demo data, not worth the complexity of finer-grained idempotency.
_TRANSIENT_CONNECTION_ERRORS = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadTimeout)


def seed_orders(plans: list[dict]) -> tuple[Counter, int]:
    """Actually create each planned order via the real service layer, then
    walk it through its status progression. Returns (status_counts,
    total_notifications_created).
    """
    status_counts: Counter = Counter()
    total_notifications = 0

    for i, plan in enumerate(plans):
        try:
            final_status, notifications = _seed_one_order(plan)
        except _TRANSIENT_CONNECTION_ERRORS:
            print(f"  ...transient connection error on order {i + 1}, retrying once")
            final_status, notifications = _seed_one_order(plan)

        if final_status is not None:
            total_notifications += notifications
            status_counts[final_status] += 1

        if (i + 1) % 25 == 0:
            print(f"  ...{i + 1}/{NUM_ORDERS} orders seeded")

    return status_counts, total_notifications


def count_demo_customers() -> int:
    response = (
        supabase.table("customers")
        .select("id", count="exact", head=True)
        .ilike("email", f"%@{DEMO_EMAIL_DOMAIN}")
        .execute()
    )
    return response.count or 0


def count_demo_orders() -> int:
    demo_customers = (
        supabase.table("customers")
        .select("id")
        .ilike("email", f"%@{DEMO_EMAIL_DOMAIN}")
        .execute()
    )
    customer_ids = [row["id"] for row in demo_customers.data]
    if not customer_ids:
        return 0
    response = (
        supabase.table("orders")
        .select("id", count="exact", head=True)
        .in_("customer_id", customer_ids)
        .execute()
    )
    return response.count or 0


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
    print(f"Target: {NUM_CUSTOMERS} customers, {NUM_ORDERS} orders over the last 12 months\n")

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
