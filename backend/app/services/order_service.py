from app.core.database import supabase
from app.services.designer_service import get_designer_options
from app.services.search_utils import sanitize_search_term
from app.services.template_service import get_template_by_id


def _find_option(options: dict, key: str, option_id: str) -> dict | None:
    return next((item for item in options[key] if item["id"] == option_id), None)


def find_or_create_customer(name: str, phone: str | None, email: str) -> str:
    """Find an existing customer by email, or create a lightweight one.
    Not order-specific despite living here (this module owns customer
    creation because order checkout was its first caller) — reused as-is
    by the chat widget's identity capture (see api/routes/chat.py),
    which has no phone number to offer (`phone` is nullable on
    `customers`, so `None` is a real, valid value here, not a workaround).
    """
    existing = (
        supabase.table("customers").select("id").eq("email", email).limit(1).execute()
    )
    if existing.data:
        return existing.data[0]["id"]

    created = (
        supabase.table("customers")
        .insert({"name": name, "phone": phone, "email": email})
        .execute()
    )
    return created.data[0]["id"]


def create_order(
    order: dict,
    *,
    created_at: str | None = None,
    pickup_date: str | None = None,
    pickup_time: str | None = None,
) -> str | None:
    """Create a pending order for a customer.

    `created_at`/`pickup_date`/`pickup_time` are keyword-only overrides
    used exclusively by tools/demo_data_seed.py to backdate seeded orders
    across a realistic historical range (see docs/SPRINT2_DEMO_DATA.md).
    The real call site — `POST /orders`'s route — never passes them, so
    `created_at` keeps its normal DB-generated `now()` value and
    `pickup_date`/`pickup_time` stay unset, exactly as before this
    function gained these parameters.
    """
    # get_template_by_id() deliberately doesn't filter `active` (the admin
    # catalog view needs inactive templates too, see its own docstring) --
    # so it's checked explicitly here, at the one authoritative order-
    # creation choke point every channel (Website/Chat/WhatsApp/direct API)
    # goes through. A deactivated template must be rejected exactly like a
    # nonexistent one: the customer never sees the difference between "no
    # such cake" and "not offered anymore". cake_size/flavor/filling/
    # frosting below already only ever search get_designer_options()'s
    # active-filtered lists, so they're already covered without needing the
    # same explicit check.
    template = get_template_by_id(order["template_id"])
    if template is None or not template.get("active"):
        return None

    options = get_designer_options()
    cake_size = _find_option(options, "cake_sizes", order["cake_size_id"])
    flavor = _find_option(options, "flavors", order["flavor_id"])
    filling = _find_option(options, "fillings", order["filling_id"])
    frosting = _find_option(options, "frostings", order["frosting_id"])

    if not all([cake_size, flavor, filling, frosting]):
        raise ValueError("Invalid cake size, flavor, filling, or frosting selection")

    total_price = template["base_price"] + cake_size["price_adjustment"]

    customer_id = find_or_create_customer(
        order["customer_name"], order["customer_phone"], order["customer_email"]
    )

    configuration = {
        "cakeSize": cake_size,
        "flavor": flavor,
        "filling": filling,
        "frosting": frosting,
    }

    insert_payload = {
        "customer_id": customer_id,
        "template_id": order["template_id"],
        "status": "pending",
        "total_price": total_price,
        "configuration": configuration,
        "notes": order["notes"],
    }
    if created_at is not None:
        insert_payload["created_at"] = created_at
    if pickup_date is not None:
        insert_payload["pickup_date"] = pickup_date
    if pickup_time is not None:
        insert_payload["pickup_time"] = pickup_time

    response = supabase.table("orders").insert(insert_payload).execute()
    return response.data[0]["id"]


# --- Admin order management (Epic 1 — Backoffice) --------------------------
# Everything below reads/updates the same `orders` table create_order()
# writes to above. Kept in this file rather than a separate admin-only
# service module because it's the same domain (orders), just a different,
# staff-facing set of operations on it — matching the project's convention
# of one service file per business domain, not per audience.

# Must match the `orders.status` check constraint in
# supabase/migrations/20260729120000_initial_schema.sql.
ORDER_STATUSES = (
    "pending",
    "confirmed",
    "in_progress",
    "ready",
    "completed",
    "cancelled",
)

# Resource embedding (PostgREST feature already available via the same
# supabase-py client, no new dependency): fetches the order's customer and
# template in one query instead of three separate round trips.
_ORDER_DETAIL_SELECT = (
    "*, customers(id, name, email, phone), cake_templates(id, name, category, preview_image)"
)


def _page_to_range(page: int, page_size: int) -> tuple[int, int]:
    """Convert a 1-based page number + page size into the 0-based,
    inclusive (start, end) range `.range()` expects."""
    start = (page - 1) * page_size
    end = start + page_size - 1
    return start, end


def _search_customer_ids(search: str) -> list[str]:
    """Resolve a free-text search term to matching customer ids (name,
    email, or phone — an order itself has no free-text field worth
    searching). A separate query rather than one filtered join: PostgREST
    doesn't support OR-filtering across an embedded resource in a single
    simple call, and two small, readable queries beat one clever one.
    """
    safe_search = sanitize_search_term(search)
    if not safe_search:
        return []

    response = (
        supabase.table("customers")
        .select("id")
        .or_(f"name.ilike.%{safe_search}%,email.ilike.%{safe_search}%,phone.ilike.%{safe_search}%")
        .execute()
    )
    return [row["id"] for row in response.data]


def list_orders(
    search: str | None = None,
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
) -> dict:
    """Search/filter/paginate orders for the admin order list."""
    query = supabase.table("orders").select(_ORDER_DETAIL_SELECT, count="exact")

    if status:
        query = query.eq("status", status)

    if search:
        customer_ids = _search_customer_ids(search)
        if not customer_ids:
            return {"items": [], "total": 0, "page": page, "pageSize": page_size}
        query = query.in_("customer_id", customer_ids)

    start, end = _page_to_range(page, page_size)
    response = query.order("created_at", desc=True).range(start, end).execute()

    return {
        "items": response.data,
        "total": response.count or 0,
        "page": page,
        "pageSize": page_size,
    }


def get_order_by_id(order_id: str) -> dict | None:
    """Fetch one order with its customer and template joined in."""
    response = (
        supabase.table("orders")
        .select(_ORDER_DETAIL_SELECT)
        .eq("id", order_id)
        .maybe_single()
        .execute()
    )
    return response.data if response is not None else None


def update_order_status(order_id: str, new_status: str) -> dict:
    """Update an order's status and return the updated, joined order.

    Raises ValueError for a status outside ORDER_STATUSES, mirroring the DB
    check constraint but checked here first so a bad status is a clean 400
    rather than a raw database error. Assumes the order's existence has
    already been confirmed by the caller (see
    app/api/routes/admin/orders.py, which needs the *previous* status for
    the audit log entry anyway, so it already fetches the order first).
    """
    if new_status not in ORDER_STATUSES:
        raise ValueError(f"Invalid status: {new_status}")

    supabase.table("orders").update({"status": new_status}).eq("id", order_id).execute()
    return get_order_by_id(order_id)


def get_orders_for_customer(customer_id: str) -> list[dict]:
    """All orders for one customer, newest first — the same joined shape
    as list_orders/get_order_by_id. Used by the Customers screen
    (app/services/customer_service.py) so it reuses this domain's one
    query shape instead of duplicating it (Epic 1.2 — Customer Management
    & CRM, see docs/EPIC1_CUSTOMERS.md).
    """
    response = (
        supabase.table("orders")
        .select(_ORDER_DETAIL_SELECT)
        .eq("customer_id", customer_id)
        .order("created_at", desc=True)
        .execute()
    )
    return response.data


_OPEN_ORDER_STATUSES = tuple(s for s in ORDER_STATUSES if s not in ("completed", "cancelled"))


def find_open_order_for_customer(customer_id: str) -> tuple[dict | None, str]:
    """The confidently-identifiable "current" order for an inbound
    message's customer (Step 3 — see inbound_service.py). Never guesses:
    exactly one open (not completed/cancelled) order is a confident
    match; zero is "none"; more than one is "ambiguous" — a human has to
    say which order the customer means, since the AI Agent must not
    accidentally answer about the wrong cake (see docstring on
    agent_service.draft_reply_to_inbound_message).

    "Open" rather than "most recent" on purpose: a customer messaging in
    is far more likely asking about an order still in flight than a
    finished one, and this project has no stronger signal today (e.g.
    which order they're referring to in their own words) to disambiguate
    with — a documented heuristic, not a claim of certainty.

    Returns (order, match_status) where match_status is one of "matched",
    "ambiguous", "none" — mirrors inbound_messages.order_match_status.
    """
    orders = get_orders_for_customer(customer_id)
    open_orders = [o for o in orders if o["status"] in _OPEN_ORDER_STATUSES]
    if len(open_orders) == 1:
        return open_orders[0], "matched"
    if len(open_orders) > 1:
        return None, "ambiguous"
    return None, "none"
