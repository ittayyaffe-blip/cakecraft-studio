#!/usr/bin/env python
"""CakeCraft Studio — ADDITIVE presentation/demo dataset (this week + next
week), layered on top of the existing seeded history without touching it.

Unlike tools/demo_data_seed.py (which deletes and fully re-seeds its own
~2000-customer/~2500-order historical dataset), this script is purely
additive: it never deletes or modifies an existing row, and refuses to run
twice (see idempotency check in main()).

Two customer groups, for two different reasons (see the "PRESENTATION
DATASET EXPANSION" task write-up):

  - ~270 bulk orders across a pool of unique synthetic customers (own
    reserved email domain, PRESENTATION_EMAIL_DOMAIN) -- realistic CRM
    variety, matching the existing seeder's own name pool/conventions.
  - ~30 orders across 10 named "hero" customers who all share the
    presenter's REAL contact details (HERO_EMAIL/HERO_PHONE), for live
    Email/WhatsApp demo testing. order_service.find_or_create_customer
    (and therefore order_service.create_order, which calls it internally)
    matches strictly by email -- verified live before writing this script
    -- so routing all 10 heroes' orders through create_order() as-is
    would silently collapse all of them into whichever hero happened to
    be created first. The 10 hero customer rows are therefore inserted
    directly (bypassing that one dedup step only, by construction) with
    10 different realistic names sharing the one real email/phone, then
    each hero's own orders are inserted via _insert_order_for_customer()
    below, which replicates create_order()'s own pricing/configuration
    computation exactly (same serving_band_service call, same formula) --
    nothing about this invents new business logic, it only skips the
    customer-identification step that doesn't apply once the customer_id
    is already known. Multiple customer rows sharing one email is not a
    new failure mode this introduces: customer_service.find_customer_by_email
    already has an explicit "ambiguous -- don't guess" contract for
    exactly this case (ambiguous=True, customer=None), so a real inbound
    message from HERO_EMAIL is handled safely, not misattributed.

Usage (from anywhere, run with the project's venv):

    <venv>/python tools/presentation_seed.py --simulate   # plan only, no DB writes
    <venv>/python tools/presentation_seed.py               # writes for real

Never calls notification_service.send()/submit_for_approval()/approve() --
every notification created by this script stays at 'draft'. Never touches
an existing order/customer/notification row.
"""

import random
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

import demo_data_seed as base  # noqa: E402 -- reuses FIRST_NAMES/LAST_NAMES/NOTE_TEMPLATES/COLLECTION_WEIGHTS

from app.core.database import supabase  # noqa: E402
from app.services import (  # noqa: E402
    audit_service,
    designer_service,
    notification_service,
    order_service,
    serving_band_service,
    template_service,
)

# --- Configuration -----------------------------------------------------

# A SECOND reserved test domain, deliberately distinct from
# demo_data_seed.py's own DEMO_EMAIL_DOMAIN -- this batch must be
# independently identifiable, and must never be swept up if the (much
# more destructive) delete-and-reseed seeder is ever run again.
PRESENTATION_EMAIL_DOMAIN = "presentation.maisondegateau.test"

HERO_EMAIL = "ittayyaffe@gmail.com"
HERO_PHONE = "+972545446601"
HERO_NAMES = [
    "Camille Rousseau", "Julien Fontaine", "Aurelie Mercier", "Thomas Lambert",
    "Charlotte Blanchard", "Antoine Girard", "Elise Faure", "Maxime Gauthier",
    "Pauline Renard", "Nicolas Perrin",
]
ORDERS_PER_HERO = 3  # 10 x 3 = 30

NUM_BULK_CUSTOMERS = 200
NUM_BULK_ORDERS = 270  # + 30 hero orders = 300 total

random.seed(20260816_02)  # distinct, fixed seed from demo_data_seed.py's own 20260807
NOW = datetime.now(timezone.utc)

# 8-75 guests only -- the >75 Custom Event rule is never exercised by an
# automated seed script (see serving_band_service.is_standard_ordering_eligible).
BAND_RANGES = {"SMALL": (8, 12), "MEDIUM": (13, 20), "LARGE": (21, 30), "XL": (31, 50), "EVENT": (51, 75)}
BAND_WEIGHTS_DEFAULT = {"SMALL": 0.30, "MEDIUM": 0.30, "LARGE": 0.20, "XL": 0.12, "EVENT": 0.08}
# Weddings/Corporate events realistically skew toward bigger guest counts.
BAND_WEIGHTS_BIG_EVENT = {"SMALL": 0.05, "MEDIUM": 0.15, "LARGE": 0.30, "XL": 0.30, "EVENT": 0.20}

BUCKET_WEIGHTS = {"today": 0.30, "tomorrow": 0.15, "2-3d": 0.25, "this_week": 0.18, "next_week": 0.12}
PROGRESSION = ["confirmed", "in_progress", "ready", "completed"]


def pick_guest_count(category: str) -> int:
    weights = BAND_WEIGHTS_BIG_EVENT if category in ("Wedding", "Corporate") else BAND_WEIGHTS_DEFAULT
    band = random.choices(list(weights), weights=list(weights.values()), k=1)[0]
    lo, hi = BAND_RANGES[band]
    return random.randint(lo, hi)


def valid_pickup_slots() -> dict[str, list[datetime]]:
    """Every valid (non-Monday, 09:00-18:00, 30-min-interval, not-in-the-
    past) pickup datetime over the next 14 days, bucketed by how far out
    it is -- mirrors validate_pickup_datetime's own three rules exactly
    (never independently re-implemented, just walked forward) so every
    slot this produces is guaranteed acceptable to the real backend.
    """
    buckets: dict[str, list[datetime]] = {"today": [], "tomorrow": [], "2-3d": [], "this_week": [], "next_week": []}
    today = NOW.date()
    for offset in range(0, 14):
        d = today + timedelta(days=offset)
        if d.weekday() == 0:  # Monday -- closed
            continue
        if offset <= 0:
            bucket = "today"
        elif offset == 1:
            bucket = "tomorrow"
        elif offset <= 3:
            bucket = "2-3d"
        elif offset <= 7:
            bucket = "this_week"
        else:
            bucket = "next_week"
        for hour in range(9, 19):
            for minute in (0, 30):
                if hour == 18 and minute == 30:
                    continue  # 18:00 is the last valid slot
                dt = datetime.combine(d, time(hour, minute), tzinfo=timezone.utc)
                if dt <= NOW:
                    continue
                buckets[bucket].append(dt)
    return buckets


def pick_pickup_dt(slots: dict[str, list[datetime]]) -> datetime:
    non_empty = {b: w for b, w in BUCKET_WEIGHTS.items() if slots.get(b)}
    bucket = random.choices(list(non_empty), weights=list(non_empty.values()), k=1)[0]
    return random.choice(slots[bucket])


def choose_status(pickup_dt: datetime) -> str:
    """Status is always causally consistent with pickup_dt (never
    'completed' for a pickup that hasn't happened yet) -- Step 6's target
    percentages are approximated by the bucket spread above, not forced
    independently of this constraint (see the final report for the
    actual, as-seeded percentages).
    """
    if random.random() < 0.03:
        return "cancelled"
    days = (pickup_dt.date() - NOW.date()).days
    if days <= 0:
        return random.choices(["ready", "completed", "in_progress"], weights=[0.35, 0.45, 0.20], k=1)[0]
    if days == 1:
        return random.choices(["in_progress", "ready", "confirmed"], weights=[0.45, 0.35, 0.20], k=1)[0]
    if days <= 3:
        return random.choices(["confirmed", "in_progress", "ready", "pending"], weights=[0.35, 0.40, 0.15, 0.10], k=1)[0]
    if days <= 7:
        return random.choices(["confirmed", "pending", "in_progress"], weights=[0.60, 0.25, 0.15], k=1)[0]
    return random.choices(["pending", "confirmed"], weights=[0.55, 0.45], k=1)[0]


def choose_note(category: str) -> str | None:
    return random.choice(base.NOTE_TEMPLATES.get(category, [None]))


# --- Idempotency ------------------------------------------------------------


def already_seeded() -> bool:
    """Checks for actual ORDERS (the real deliverable), not merely
    customer rows -- a customer row alone can legitimately exist from a
    prior run that was interrupted between creating hero customers and
    writing any orders (create_hero_customers() is itself idempotent by
    name, so re-running after exactly that kind of partial failure must
    be able to proceed, not be blocked as "already done"). Specifically
    scoped to THIS batch's own presentation-domain customers / hero
    names, not merely "a customer exists with HERO_EMAIL" -- that email
    is the presenter's own real address, already used by a real
    pre-existing customer from earlier manual testing (name "Ittay
    Yaffe", unrelated to this seeder) before this script ever ran.
    """
    presentation_ids = [
        c["id"]
        for c in supabase.table("customers").select("id").like("email", f"%@{PRESENTATION_EMAIL_DOMAIN}").execute().data
    ]
    hero_ids = [
        c["id"]
        for c in supabase.table("customers").select("id").eq("email", HERO_EMAIL).in_("name", HERO_NAMES).execute().data
    ]
    candidate_ids = presentation_ids + hero_ids
    if not candidate_ids:
        return False
    orders = supabase.table("orders").select("id", count="exact").in_("customer_id", candidate_ids).limit(1).execute()
    return (orders.count or 0) > 0


# --- Catalog / customer pools -------------------------------------------


def build_bulk_customer_pool(n: int) -> list[dict]:
    used_emails: set[str] = set()
    customers = []
    while len(customers) < n:
        first = random.choice(base.FIRST_NAMES)
        last = random.choice(base.LAST_NAMES)
        email = f"{first.lower()}.{last.lower()}@{PRESENTATION_EMAIL_DOMAIN}"
        if email in used_emails:
            email = f"{first.lower()}.{last.lower()}{len(customers)}@{PRESENTATION_EMAIL_DOMAIN}"
        used_emails.add(email)
        phone = f"+33 6 {random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)} {random.randint(10, 99)}"
        customers.append({"name": f"{first} {last}", "email": email, "phone": phone})
    return customers


def create_hero_customers() -> list[str]:
    """Pre-creates (or, on a partial re-run, finds) the 10 hero customer
    rows directly -- see module docstring for why this bypasses
    find_or_create_customer's own email-based dedup, and why that's safe.
    """
    ids = []
    for name in HERO_NAMES:
        existing = supabase.table("customers").select("id").eq("email", HERO_EMAIL).eq("name", name).execute()
        if existing.data:
            ids.append(existing.data[0]["id"])
            continue
        created = supabase.table("customers").insert({"name": name, "phone": HERO_PHONE, "email": HERO_EMAIL}).execute()
        ids.append(created.data[0]["id"])
    return ids


# --- Order creation -------------------------------------------------------


def _insert_order_for_customer(customer_id: str, template: dict, designer_options: dict, guest_count: int, notes: str | None, pickup_dt: datetime) -> dict:
    """Used only for hero orders (known customer_id, so create_order()'s
    own find-or-create step doesn't apply) -- otherwise an exact replica
    of create_order()'s own guest-count-driven price/configuration
    computation (same serving_band_service call, same formula), not a
    reinvented one.
    """
    band = serving_band_service.compute_serving_band(guest_count)
    size_name = serving_band_service.BAND_TO_SIZE_NAME[band]
    cake_size = next(s for s in designer_options["cake_sizes"] if s["name"] == size_name)
    flavor = random.choice(designer_options["flavors"])
    filling = random.choice(designer_options["fillings"])
    frosting = random.choice(designer_options["frostings"])
    total_price = template["base_price"] + cake_size["price_adjustment"]
    configuration = {"cakeSize": cake_size, "flavor": flavor, "filling": filling, "frosting": frosting, "guestCount": guest_count}

    inserted = (
        supabase.table("orders")
        .insert(
            {
                "customer_id": customer_id,
                "template_id": template["id"],
                "status": "pending",
                "total_price": total_price,
                "configuration": configuration,
                "notes": notes,
                "pickup_date": pickup_dt.date().isoformat(),
                "pickup_time": pickup_dt.time().isoformat(),
            }
        )
        .execute()
    )
    return order_service.get_order_by_id(inserted.data[0]["id"])


def progress_and_draft(order_row: dict, final_status: str) -> int:
    """pending -> final_status via the real update_order_status/
    audit_service pipeline, with a real draft notification for the
    initial 'pending' event and each subsequent step -- exactly what the
    real order-creation route and admin status-update route each do.
    NEVER calls submit_for_approval/approve/send: every notification this
    creates stays at 'draft'. Returns how many notifications were created.
    """
    drafted = 0
    if notification_service.create_notification_for_order_event(order_row, "pending") is not None:
        drafted += 1
    if final_status == "pending":
        return drafted

    steps = ["cancelled"] if final_status == "cancelled" and random.random() < 0.5 else (
        ["confirmed", "cancelled"] if final_status == "cancelled" else PROGRESSION[: PROGRESSION.index(final_status) + 1]
    )
    current = order_row
    previous = "pending"
    for status in steps:
        current = order_service.update_order_status(current["id"], status)
        audit_service.record_event(
            actor_id=None, action="order.status_changed", entity_type="orders",
            entity_id=current["id"], before={"status": previous}, after={"status": status},
        )
        if notification_service.create_notification_for_order_event(current, status) is not None:
            drafted += 1
        previous = status
    return drafted


# --- Planning (pure, no DB access -- mirrors demo_data_seed.py's own split) -


def plan_bulk_orders(customers: list[dict], templates_by_category: dict, slots: dict, designer_options: dict) -> list[dict]:
    categories = [c for c in base.COLLECTION_WEIGHTS if templates_by_category.get(c)]
    category_weights = [base.COLLECTION_WEIGHTS[c] for c in categories]
    indices = base._assign_customer_indices(len(customers), [1.0] * len(customers), NUM_BULK_ORDERS)

    plans = []
    for idx in indices:
        category = random.choices(categories, weights=category_weights, k=1)[0]
        template = random.choice(templates_by_category[category])
        pickup_dt = pick_pickup_dt(slots)
        plans.append(
            {
                "customer": customers[idx],
                "category": category,
                "template": template,
                "flavor": random.choice(designer_options["flavors"]),
                "filling": random.choice(designer_options["fillings"]),
                "frosting": random.choice(designer_options["frostings"]),
                "guest_count": pick_guest_count(category),
                "notes": choose_note(category),
                "pickup_dt": pickup_dt,
                "final_status": choose_status(pickup_dt),
            }
        )
    return plans


def plan_hero_orders(hero_ids: list[str], templates_by_category: dict, slots: dict) -> list[dict]:
    categories = [c for c in base.COLLECTION_WEIGHTS if templates_by_category.get(c)]
    category_weights = [base.COLLECTION_WEIGHTS[c] for c in categories]
    plans = []
    for hero_id in hero_ids:
        for _ in range(ORDERS_PER_HERO):
            category = random.choices(categories, weights=category_weights, k=1)[0]
            template = random.choice(templates_by_category[category])
            pickup_dt = pick_pickup_dt(slots)
            plans.append(
                {
                    "customer_id": hero_id,
                    "category": category,
                    "template": template,
                    "guest_count": pick_guest_count(category),
                    "notes": choose_note(category),
                    "pickup_dt": pickup_dt,
                    "final_status": choose_status(pickup_dt),
                }
            )
    return plans


def print_plan_report(bulk_plans: list[dict], hero_plans: list[dict]) -> None:
    all_plans = bulk_plans + hero_plans
    total = len(all_plans)
    print(f"\n--- Plan report ({total} orders: {len(bulk_plans)} bulk + {len(hero_plans)} hero) ---")
    print("By collection:", dict(Counter(p["category"] for p in all_plans).most_common()))
    print("By status:", {k: f"{v} ({v / total:.0%})" for k, v in Counter(p["final_status"] for p in all_plans).most_common()})

    def band_of(gc: int) -> str:
        for name, (lo, hi) in BAND_RANGES.items():
            if lo <= gc <= hi:
                return name
        return "?"

    print("By serving band:", dict(Counter(band_of(p["guest_count"]) for p in all_plans).most_common()))

    def bucket_of(dt: datetime) -> str:
        days = (dt.date() - NOW.date()).days
        if days <= 0:
            return "today"
        if days == 1:
            return "tomorrow"
        if days <= 3:
            return "2-3 days"
        if days <= 7:
            return "this week"
        return "next week"

    print("By pickup timing:", dict(Counter(bucket_of(p["pickup_dt"]) for p in all_plans).most_common()))
    max_gc, max_band = max(((p["guest_count"], band_of(p["guest_count"])) for p in all_plans), key=lambda t: t[0])
    print(f"Max guest count planned: {max_gc} ({max_band}) -- must be <=75")


def main() -> None:
    simulate = "--simulate" in sys.argv
    print("CakeCraft Studio — Presentation Dataset Seeder" + (" (SIMULATION — no database writes)" if simulate else ""))
    print(f"Target: {NUM_BULK_ORDERS} bulk orders + {len(HERO_NAMES) * ORDERS_PER_HERO} hero orders (~{NUM_BULK_ORDERS + len(HERO_NAMES) * ORDERS_PER_HERO} total)\n")

    if not simulate and already_seeded():
        print("ABORTING: presentation data already exists (found a customer on "
              f"@{PRESENTATION_EMAIL_DOMAIN} or with email={HERO_EMAIL}). This script is additive-only "
              "and refuses to create a second batch. Nothing was written.")
        return

    templates = template_service.get_active_templates()
    if not templates:
        print("ERROR: no active cake templates found — nothing to seed against.")
        return
    templates_by_category: dict[str, list[dict]] = {}
    for t in templates:
        templates_by_category.setdefault(t["category"], []).append(t)

    designer_options = designer_service.get_designer_options()
    missing = [k for k in ("cake_sizes", "flavors", "fillings", "frostings") if not designer_options[k]]
    if missing:
        print(f"ERROR: designer options missing: {missing} — nothing to seed against.")
        return

    slots = valid_pickup_slots()
    if not any(slots.values()):
        print("ERROR: no valid pickup slots found in the next 14 days — nothing to seed.")
        return

    bulk_customers = build_bulk_customer_pool(NUM_BULK_CUSTOMERS)
    bulk_plans = plan_bulk_orders(bulk_customers, templates_by_category, slots, designer_options)
    hero_plans = plan_hero_orders(HERO_NAMES, templates_by_category, slots)  # placeholder ids, replaced below if writing

    print_plan_report(bulk_plans, hero_plans)

    if simulate:
        print("\nSimulation only — nothing was written.")
        return

    print("\nCreating hero customers...")
    hero_ids = create_hero_customers()
    hero_plans = plan_hero_orders(hero_ids, templates_by_category, slots)  # re-plan with real customer ids

    print("Writing bulk orders...")
    status_counts: Counter = Counter()
    total_notifications = 0
    for i, plan in enumerate(bulk_plans, start=1):
        order_id = order_service.create_order(
            {
                "template_id": plan["template"]["id"],
                "flavor_id": plan["flavor"]["id"],
                "filling_id": plan["filling"]["id"],
                "frosting_id": plan["frosting"]["id"],
                "guest_count": plan["guest_count"],
                "customer_name": plan["customer"]["name"],
                "customer_phone": plan["customer"]["phone"],
                "customer_email": plan["customer"]["email"],
                "notes": plan["notes"],
            },
            pickup_date=plan["pickup_dt"].date().isoformat(),
            pickup_time=plan["pickup_dt"].time().isoformat(),
        )
        if order_id is None:
            print(f"  ...skipped order {i} (template lookup failed)")
            continue
        order_row = order_service.get_order_by_id(order_id)
        total_notifications += progress_and_draft(order_row, plan["final_status"])
        status_counts[plan["final_status"]] += 1
        if i % 50 == 0:
            print(f"  ...{i}/{len(bulk_plans)} bulk orders written")

    print("Writing hero orders...")
    for plan in hero_plans:
        order_row = _insert_order_for_customer(
            plan["customer_id"], plan["template"], designer_options, plan["guest_count"], plan["notes"], plan["pickup_dt"]
        )
        total_notifications += progress_and_draft(order_row, plan["final_status"])
        status_counts[plan["final_status"]] += 1

    print("\nDone.")
    print(f"  Orders written: {sum(status_counts.values())} (target ~{NUM_BULK_ORDERS + len(HERO_NAMES) * ORDERS_PER_HERO})")
    print(f"  By final status: {dict(status_counts)}")
    print(f"  Notifications drafted: {total_notifications}")


if __name__ == "__main__":
    main()
